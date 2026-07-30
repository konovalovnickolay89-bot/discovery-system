"""Optional PydanticAI structured capture.

``used_ai`` is True only when a live provider (openai|xai) successfully runs.
``function`` and deterministic fallback always report used_ai=False.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .config import get_settings
from .models import CaptureDraft, Level

log = logging.getLogger("casual_board.agents")


def _slug_title(text: str, n: int = 10) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text)
    title = " ".join(words[:n]) if words else "Capture"
    if len(title) > 100:
        title = title[:97] + "…"
    return title[0].upper() + title[1:] if title else "Capture"


def capture_without_ai(note: str) -> CaptureDraft:
    lower = note.lower()
    tags = ["capture"]
    if any(w in lower for w in ("recipe", "dish", "sauce", "mise", "cook")):
        tags.append("recipe")
    if any(w in lower for w in ("remind", "tomorrow", "don't forget")):
        tags.append("reminder")
    level = (
        Level.warn
        if any(w in lower for w in ("urgent", "allergen", "critical"))
        else Level.info
    )
    return CaptureDraft(
        title=_slug_title(note),
        body=note[:800],
        tags=tags,
        level=level,
        suggested_when="today",
    )


def capture_with_ai(note: str) -> tuple[CaptureDraft, bool, str]:
    """Return (draft, used_ai, provider_id).

    used_ai is True only for a successful live openai/xai model call.
    """
    settings = get_settings()
    if not settings.enable_pydantic_ai:
        return capture_without_ai(note), False, "none"

    provider = settings.resolved_ai_provider()
    if provider == "none":
        return capture_without_ai(note), False, "none"

    try:
        from pydantic_ai import Agent, ModelResponse, TextPart
        from pydantic_ai.models.function import FunctionModel
    except Exception as e:  # noqa: BLE001
        log.info("pydantic-ai unavailable: %s", e)
        return capture_without_ai(note), False, "unavailable"

    def _fn(messages: list[Any], info: Any) -> ModelResponse:
        user_text = note
        for m in reversed(messages):
            for p in getattr(m, "parts", None) or []:
                if type(p).__name__ == "UserPromptPart" and isinstance(
                    getattr(p, "content", None), str
                ):
                    user_text = p.content
                    break
        draft = capture_without_ai(user_text.replace("User note:", "").strip())
        return ModelResponse(parts=[TextPart(content=draft.model_dump_json())])

    model: Any
    live = False
    model_id = settings.resolved_ai_model()

    if provider == "function":
        model = FunctionModel(_fn, model_name="casual-board-capture")
        live = False
    elif provider == "xai":
        if not os.environ.get("XAI_API_KEY"):
            log.warning("CASUAL_BOARD_AI_PROVIDER=xai but XAI_API_KEY unset — fallback")
            return capture_without_ai(note), False, "xai-missing-key"
        os.environ.setdefault("OPENAI_API_KEY", os.environ["XAI_API_KEY"])
        if "OPENAI_BASE_URL" not in os.environ and "OPENAI_API_BASE" not in os.environ:
            os.environ.setdefault("OPENAI_BASE_URL", "https://api.x.ai/v1")
        model = model_id if model_id.startswith("openai:") else f"openai:{model_id}"
        live = True
    elif provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            log.warning("CASUAL_BOARD_AI_PROVIDER=openai but OPENAI_API_KEY unset — fallback")
            return capture_without_ai(note), False, "openai-missing-key"
        model = model_id if ":" in model_id else f"openai:{model_id}"
        live = True
    else:
        return capture_without_ai(note), False, provider

    try:
        agent: Agent[None, CaptureDraft] = Agent(
            model,
            output_type=CaptureDraft,
            system_prompt=(
                "Turn a rough kitchen/systems note into a short CaptureDraft: "
                "title, body, tags, level info|warn, suggested_when."
            ),
        )
        result = agent.run_sync(f"User note:\n{note}")
        out = result.output
        if not isinstance(out, CaptureDraft):
            out = CaptureDraft.model_validate(out)
        if live:
            return out, True, provider
        return out, False, "function"
    except Exception as e:  # noqa: BLE001
        log.warning("pydantic-ai capture failed, fallback: %s", e)
        return capture_without_ai(note), False, f"{provider}-error"
