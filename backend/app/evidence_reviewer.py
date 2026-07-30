"""Optional server-side PydanticAI evidence reviewer (no retrieval/shell/graph tools).

Runs after Graph Recall and before the deterministic evidence gate.
Default provider=none: skip model call; gate still validates with Pydantic.

Live providers (API process env only — never worker / VITE / browser):
  CASUAL_BOARD_EVIDENCE_AI_PROVIDER=mistral|openai|xai|function|none
  CASUAL_BOARD_EVIDENCE_AI_MODEL=mistral:mistral-small-latest
  MISTRAL_API_KEY / OPENAI_API_KEY / XAI_API_KEY
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .config import get_settings
from .evidence_models import ModelMeta

log = logging.getLogger("casual_board.evidence_reviewer")

# Injectable for tests: (payload) -> reviewed dict | raises
EvidenceReviewerFn = Callable[[dict[str, Any]], dict[str, Any]]
# Injectable live agent: (model, user_prompt) -> dict | raises
LiveReviewRunnerFn = Callable[[str, str], dict[str, Any]]

DEFAULT_MISTRAL_MODEL = "mistral:mistral-small-latest"
SUPPORTED_LIVE = frozenset({"mistral", "openai", "xai"})


class EvidenceReviewerUnavailable(Exception):
    """Configured provider failed or is unavailable."""


def evidence_ai_provider() -> str:
    s = get_settings()
    raw = (getattr(s, "evidence_ai_provider", None) or "none").strip().lower()
    if raw in {"", "off", "disabled", "false"}:
        return "none"
    if raw in {"none", "function", "openai", "xai", "mistral"}:
        return raw
    return "none"


def resolve_evidence_model(provider: str | None = None) -> str:
    """Return pydantic-ai model id. Default Mistral model when provider=mistral."""
    prov = provider or evidence_ai_provider()
    s = get_settings()
    configured = (getattr(s, "evidence_ai_model", None) or "").strip()
    if configured:
        if prov == "mistral" and ":" not in configured:
            return f"mistral:{configured}"
        if prov == "openai" and ":" not in configured:
            return f"openai:{configured}"
        if prov == "xai" and ":" not in configured:
            return f"openai:{configured}"  # xAI OpenAI-compatible
        return configured
    if prov == "mistral":
        return DEFAULT_MISTRAL_MODEL
    if prov == "openai":
        return "openai:gpt-4o-mini"
    if prov == "xai":
        return "openai:grok-2-latest"
    return ""


def require_evidence_api_key(provider: str) -> None:
    """Keys only from process env (API systemd EnvironmentFile). Never log values."""
    if provider == "mistral":
        if not (os.environ.get("MISTRAL_API_KEY") or "").strip():
            raise EvidenceReviewerUnavailable("mistral_key_missing")
    elif provider == "openai":
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            raise EvidenceReviewerUnavailable("openai_key_missing")
    elif provider == "xai":
        if not (os.environ.get("XAI_API_KEY") or "").strip():
            raise EvidenceReviewerUnavailable("xai_key_missing")
    else:
        raise EvidenceReviewerUnavailable("unsupported_provider")


def _allowed_citation_sets(
    kitchen_memory: list[dict[str, Any]],
    registered_sources: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    allowed_paths = {
        str(m.get("path") or m.get("path_or_url") or "") for m in kitchen_memory
    }
    allowed_ids = {str(m.get("source_id") or "") for m in kitchen_memory}
    for s in registered_sources:
        allowed_ids.add(str(s.get("id") or s.get("source_id") or ""))
        allowed_paths.add(str(s.get("graph_path") or s.get("url") or ""))
    return allowed_ids, allowed_paths


def _filter_citations(
    cites: list[Any],
    *,
    allowed_ids: set[str],
    allowed_paths: set[str],
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cites or []:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("source_id") or "")
        path = str(c.get("path_or_url") or c.get("path") or "")
        if sid and sid not in allowed_ids and path not in allowed_paths:
            continue
        if path and path not in allowed_paths and sid not in allowed_ids:
            continue
        out.append(c)
    return out if out else list(fallback)


def _run_pydantic_ai_review(model_name: str, user_prompt: str) -> dict[str, Any]:
    """Tool-less Agent only. No browser/shell/graph/retrieval tools."""
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    class _Cite(BaseModel):
        source_id: str = ""
        title: str = ""
        path_or_url: str = ""
        excerpt: str = ""
        authority_tier: int = 2

    class _Reviewed(BaseModel):
        recommendation: str = ""
        safety_verdict: str = ""
        citations: list[_Cite] = Field(default_factory=list)
        confidence: float = 0.5
        unknowns_or_conflicts: list[str] = Field(default_factory=list)
        research_status: str = "not_needed"
        sources_conflict: bool = False

    # No tools registered on the agent
    agent: Agent[_Reviewed] = Agent(
        model_name,
        result_type=_Reviewed,
        system_prompt=(
            "You normalise culinary evidence claims only. "
            "You have no retrieval, shell, browser, or graph tools. "
            "Never invent citations; only use source_id/path provided in the payload."
        ),
    )
    result = agent.run_sync(user_prompt)
    data = result.data
    return data.model_dump()


def review_graph_recall_output(
    *,
    kitchen_memory: list[dict[str, Any]],
    enrichment: dict[str, Any],
    registered_sources: list[dict[str, Any]],
    recommendation: str,
    safety_verdict: str,
    reviewer: EvidenceReviewerFn | None = None,
    live_runner: LiveReviewRunnerFn | None = None,
) -> tuple[dict[str, Any], ModelMeta]:
    """
    Normalise claims/citations/unknowns/conflicts from Graph Recall + source metadata.
    Must NOT invent citations. No retrieval, shell, browser, or graph-write tools.
    """
    provider = evidence_ai_provider()
    base = {
        "recommendation": recommendation
        or enrichment.get("recommendation")
        or enrichment.get("note")
        or "",
        "safety_verdict": safety_verdict,
        "citations": [
            {
                "source_id": m.get("source_id") or "",
                "title": m.get("title") or "note",
                "path_or_url": m.get("path") or m.get("path_or_url") or "",
                "excerpt": m.get("excerpt") or m.get("finding") or "",
                "authority_tier": m.get("authority_tier") or 2,
            }
            for m in kitchen_memory
        ],
        "confidence": 0.55 if kitchen_memory else 0.15,
        "unknowns_or_conflicts": list(enrichment.get("unknowns") or [])
        + list(enrichment.get("conflicts") or []),
        "research_status": "not_needed",
        "sources_conflict": bool(enrichment.get("conflicts")),
    }
    allowed_ids, allowed_paths = _allowed_citation_sets(kitchen_memory, registered_sources)

    if reviewer is not None:
        try:
            out = reviewer(
                {
                    "kitchen_memory": kitchen_memory,
                    "enrichment": enrichment,
                    "registered_sources": registered_sources,
                    "draft": base,
                }
            )
            if not isinstance(out, dict):
                raise EvidenceReviewerUnavailable("reviewer returned non-dict")
            cites = _filter_citations(
                out.get("citations") or base["citations"],
                allowed_ids=allowed_ids,
                allowed_paths=allowed_paths,
                fallback=base["citations"],
            )
            out = {**base, **out, "citations": cites}
            return out, ModelMeta(provider="test", used_ai=False, model="fake-reviewer")
        except EvidenceReviewerUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise EvidenceReviewerUnavailable(type(e).__name__) from e

    if provider == "none":
        return base, ModelMeta(provider="none", used_ai=False, model=None)

    if provider == "function":
        unknowns = list(base["unknowns_or_conflicts"])
        if enrichment.get("conflicts"):
            unknowns.append("sources conflict disclosed by Graph Recall")
            base["sources_conflict"] = True
        base["unknowns_or_conflicts"] = unknowns
        return base, ModelMeta(provider="function", used_ai=False, model="evidence-function")

    if provider not in SUPPORTED_LIVE:
        raise EvidenceReviewerUnavailable("unsupported_provider")

    try:
        require_evidence_api_key(provider)
        model_name = resolve_evidence_model(provider)
        if not model_name:
            raise EvidenceReviewerUnavailable("no_evidence_model")

        payload = {
            "draft": base,
            "kitchen_memory": kitchen_memory,
            "registered_sources": registered_sources,
            "enrichment": enrichment,
        }
        user_prompt = (
            "Normalise this Graph Recall evidence payload. Do not invent citations.\n"
            + str(payload)[:12000]
        )

        runner = live_runner or _run_pydantic_ai_review
        out = runner(model_name, user_prompt)
        if not isinstance(out, dict):
            raise EvidenceReviewerUnavailable("invalid_model_output")
        cites = _filter_citations(
            out.get("citations") or [],
            allowed_ids=allowed_ids,
            allowed_paths=allowed_paths,
            fallback=base["citations"],
        )
        merged = {**base, **out, "citations": cites}
        # Never put secrets into model_meta
        return merged, ModelMeta(provider=provider, used_ai=True, model=model_name)
    except EvidenceReviewerUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        # category only — never message body (may contain prompt fragments)
        log.info("evidence_reviewer_failed category=%s provider=%s", type(e).__name__, provider)
        raise EvidenceReviewerUnavailable(type(e).__name__) from e
