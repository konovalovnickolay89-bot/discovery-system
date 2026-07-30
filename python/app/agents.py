"""PydanticAI agents for Casual Board.

Uses a real OpenAI-compatible model when OPENAI_API_KEY (or XAI_API_KEY) is set;
otherwise a FunctionModel that still runs through the PydanticAI agent pipeline
and validates structured output with Pydantic.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic_ai import Agent, ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from .models import CaptureDraft, LearningExpansion


def _engine_name() -> str:
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("XAI_API_KEY"):
        return "pydantic-ai:live"
    return "pydantic-ai:function"


def _model_label() -> str:
    if os.environ.get("XAI_API_KEY"):
        return os.environ.get("PYDANTIC_AI_MODEL", "xai:grok-3")
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ.get("PYDANTIC_AI_MODEL", "openai:gpt-4o-mini")
    return "function:casual-board"


def _slug_words(text: str, n: int = 8) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text)
    return " ".join(words[:n]) if words else "capture"


def _extract_user_text(messages: list[Any]) -> str:
    """Pull the latest UserPromptPart content from PydanticAI message history."""
    for m in reversed(messages):
        parts = getattr(m, "parts", None) or []
        # Prefer last user-prompt part in this message
        user_bits: list[str] = []
        for p in parts:
            kind = getattr(p, "part_kind", None) or ""
            content = getattr(p, "content", None)
            if kind in ("user-prompt", "user") and isinstance(content, str):
                user_bits.append(content)
            elif type(p).__name__ == "UserPromptPart" and isinstance(content, str):
                user_bits.append(content)
        if user_bits:
            text = user_bits[-1].strip()
            if "User note:" in text:
                text = text.split("User note:", 1)[-1].strip()
            # "Topic: x\nPrompt: y" form handled by caller
            return text
    return ""


def _capture_function(messages: list[Any], info: Any) -> ModelResponse:
    """Deterministic structured capture — still validated by PydanticAI output_type."""
    user_text = _extract_user_text(messages)

    title = _slug_words(user_text, 10)
    if len(title) > 80:
        title = title[:77] + "…"
    if not title:
        title = "Untitled capture"

    body = user_text if len(user_text) <= 800 else user_text[:797] + "…"
    tags: list[str] = ["capture"]
    lower = user_text.lower()
    if any(w in lower for w in ("recipe", "dish", "cook", "sauce", "mise", "gnocchi")):
        tags.append("recipe")
    if any(w in lower for w in ("remind", "tomorrow", "don't forget", "do not forget")):
        tags.append("reminder")

    level = "info"
    if any(w in lower for w in ("urgent", "asap", "critical", "allergen")):
        level = "warn"

    draft = {
        "title": title[0].upper() + title[1:] if title else "Capture",
        "body": body or "Empty note",
        "tags": tags,
        "level": level,
        "suggested_when": "today"
        if level == "warn"
        else ("week" if "later" in lower else "today"),
    }
    return ModelResponse(parts=[TextPart(content=json.dumps(draft))])


def _learning_function(messages: list[Any], info: Any) -> ModelResponse:
    raw = _extract_user_text(messages)
    topic = "service-rescue"
    user_text = raw
    if "Topic:" in raw or "Prompt:" in raw:
        for line in raw.splitlines():
            if line.lower().startswith("topic:"):
                topic = line.split(":", 1)[1].strip() or topic
            if line.lower().startswith("prompt:"):
                user_text = line.split(":", 1)[1].strip()

    primary = user_text if len(user_text) <= 280 else user_text[:277] + "…"
    if not primary:
        primary = f"Kitchen SOP note for {topic}"

    detail = (
        f"SOP expansion for {topic}: {user_text} "
        "Walk it at open, call it on the pass, write near-misses same shift. "
        "Keep the matrix honest; never improvise allergens under pressure."
    )
    if len(detail) > 600:
        detail = detail[:597] + "…"

    payload = {
        "topic": topic,
        "primary": primary,
        "detail": detail,
        "tags": [topic, "ai-expanded"],
    }
    return ModelResponse(parts=[TextPart(content=json.dumps(payload))])


def _build_model():
    """Prefer live model credentials; fall back to FunctionModel demo engine."""
    xai = os.environ.get("XAI_API_KEY")
    oai = os.environ.get("OPENAI_API_KEY")
    if xai:
        os.environ.setdefault("OPENAI_API_KEY", xai)
        if os.environ.get("OPENAI_BASE_URL") is None and os.environ.get("XAI_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = os.environ["XAI_BASE_URL"]
        model_id = os.environ.get("PYDANTIC_AI_MODEL", "openai:grok-3")
        return model_id
    if oai:
        return os.environ.get("PYDANTIC_AI_MODEL", "openai:gpt-4o-mini")
    return None


def capture_agent() -> Agent[None, CaptureDraft]:
    live = _build_model()
    if live:
        return Agent(
            live,
            output_type=CaptureDraft,
            system_prompt=(
                "You turn rough kitchen / systems notes into a calm journal capture "
                "for a personal CLI board. Short title, clear body, sensible tags "
                "(capture, recipe, reminder), level info|warn, suggested_when today|later|week."
            ),
        )
    return Agent(
        FunctionModel(_capture_function, model_name="casual-board-capture"),
        output_type=CaptureDraft,
        system_prompt="Structure the user note as a CaptureDraft JSON object.",
    )


def learning_agent() -> Agent[None, LearningExpansion]:
    live = _build_model()
    if live:
        return Agent(
            live,
            output_type=LearningExpansion,
            system_prompt=(
                "You write grounded kitchen / service SOP learning rows. "
                "primary = one amber teaching line (can wrap). "
                "detail = always-expanded practical steps. No fluff."
            ),
        )
    return Agent(
        FunctionModel(_learning_function, model_name="casual-board-learning"),
        output_type=LearningExpansion,
        system_prompt="Expand into LearningExpansion JSON.",
    )


def run_capture(note: str) -> CaptureDraft:
    agent = capture_agent()
    result = agent.run_sync(f"User note:\n{note}")
    out = result.output
    if not isinstance(out, CaptureDraft):
        out = CaptureDraft.model_validate(out)
    return out


def run_learning_expand(prompt: str, topic: str) -> LearningExpansion:
    agent = learning_agent()
    result = agent.run_sync(f"Topic: {topic}\nPrompt: {prompt}")
    out = result.output
    if not isinstance(out, LearningExpansion):
        out = LearningExpansion.model_validate(out)
    return out


def meta_dict() -> dict[str, str]:
    return {
        "engine": _engine_name(),
        "model": _model_label(),
        "validated_by": "pydantic",
    }
