"""Optional PydanticAI structured capture. Normal reads never require LLM."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

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
    level = Level.warn if any(w in lower for w in ("urgent", "allergen", "critical")) else Level.info
    return CaptureDraft(
        title=_slug_title(note),
        body=note[:800],
        tags=tags,
        level=level,
        suggested_when="today",
    )


def capture_with_ai(note: str) -> tuple[CaptureDraft, bool]:
    """Try PydanticAI; fall back to deterministic capture. Never raises for missing keys."""
    try:
        from pydantic_ai import Agent, ModelResponse, TextPart
        from pydantic_ai.models.function import FunctionModel
    except Exception as e:  # noqa: BLE001
        log.info("pydantic-ai unavailable: %s", e)
        return capture_without_ai(note), False

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

    # Prefer real model only when key present
    model: Any
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("XAI_API_KEY"):
        if os.environ.get("XAI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            os.environ.setdefault("OPENAI_API_KEY", os.environ["XAI_API_KEY"])
        model = os.environ.get("PYDANTIC_AI_MODEL", "openai:gpt-4o-mini")
        used_live = True
    else:
        model = FunctionModel(_fn, model_name="casual-board-capture")
        used_live = False

    try:
        agent: Agent[None, CaptureDraft] = Agent(
            model,
            output_type=CaptureDraft,
            system_prompt=(
                "Turn a rough kitchen/systems note into a short CaptureDraft JSON: "
                "title, body, tags, level info|warn, suggested_when."
            ),
        )
        result = agent.run_sync(f"User note:\n{note}")
        out = result.output
        if not isinstance(out, CaptureDraft):
            out = CaptureDraft.model_validate(out)
        return out, used_live or True
    except Exception as e:  # noqa: BLE001
        log.warning("pydantic-ai capture failed, fallback: %s", e)
        return capture_without_ai(note), False
