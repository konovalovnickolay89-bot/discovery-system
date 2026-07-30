"""Optional server-side PydanticAI evidence reviewer (no retrieval/shell/graph tools).

Runs after Graph Recall and before the deterministic evidence gate.
Default provider=none: skip model call; gate still validates with Pydantic.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .config import get_settings
from .evidence_models import ModelMeta

log = logging.getLogger("casual_board.evidence_reviewer")

# Injectable for tests: (payload) -> reviewed dict | raises
EvidenceReviewerFn = Callable[[dict[str, Any]], dict[str, Any]]


class EvidenceReviewerUnavailable(Exception):
    """Configured provider failed or is unavailable."""


def evidence_ai_provider() -> str:
    s = get_settings()
    raw = (getattr(s, "evidence_ai_provider", None) or "none").strip().lower()
    if raw in {"", "off", "disabled", "false"}:
        return "none"
    if raw in {"none", "function", "openai", "xai"}:
        return raw
    return "none"


def review_graph_recall_output(
    *,
    kitchen_memory: list[dict[str, Any]],
    enrichment: dict[str, Any],
    registered_sources: list[dict[str, Any]],
    recommendation: str,
    safety_verdict: str,
    reviewer: EvidenceReviewerFn | None = None,
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

    # Injected test reviewer
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
            # Never invent citations: only paths/ids already present
            allowed_paths = {
                str(m.get("path") or m.get("path_or_url") or "") for m in kitchen_memory
            }
            allowed_ids = {str(m.get("source_id") or "") for m in kitchen_memory}
            for s in registered_sources:
                allowed_ids.add(str(s.get("id") or s.get("source_id") or ""))
                allowed_paths.add(str(s.get("graph_path") or s.get("url") or ""))
            cites = []
            for c in out.get("citations") or base["citations"]:
                if not isinstance(c, dict):
                    continue
                sid = str(c.get("source_id") or "")
                path = str(c.get("path_or_url") or c.get("path") or "")
                if sid and sid not in allowed_ids and path not in allowed_paths:
                    continue  # drop invented
                if path and path not in allowed_paths and sid not in allowed_ids:
                    continue
                cites.append(c)
            out = {**base, **out, "citations": cites}
            return out, ModelMeta(provider="test", used_ai=False, model="fake-reviewer")
        except EvidenceReviewerUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise EvidenceReviewerUnavailable(type(e).__name__) from e

    if provider == "none":
        return base, ModelMeta(provider="none", used_ai=False, model=None)

    if provider == "function":
        # Deterministic normaliser — no live model
        unknowns = list(base["unknowns_or_conflicts"])
        if enrichment.get("conflicts"):
            unknowns.append("sources conflict disclosed by Graph Recall")
            base["sources_conflict"] = True
        base["unknowns_or_conflicts"] = unknowns
        return base, ModelMeta(provider="function", used_ai=False, model="evidence-function")

    # Live openai/xai path — structured only, no tools
    try:
        from pydantic_ai import Agent
        from pydantic import BaseModel, Field

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

        s = get_settings()
        model_name = (getattr(s, "evidence_ai_model", None) or "").strip()
        if not model_name:
            raise EvidenceReviewerUnavailable("no_evidence_model")

        # Agent has no tools by design
        agent: Agent[_Reviewed] = Agent(
            model_name,
            result_type=_Reviewed,
            system_prompt=(
                "You normalise culinary evidence claims only. "
                "You have no retrieval, shell, browser, or graph tools. "
                "Never invent citations; only use source_id/path provided in the payload."
            ),
        )
        payload = {
            "draft": base,
            "kitchen_memory": kitchen_memory,
            "registered_sources": registered_sources,
            "enrichment": enrichment,
        }
        # Avoid network in default CI — only when keys present
        import os

        if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise EvidenceReviewerUnavailable("openai_key_missing")
        if provider == "xai" and not os.environ.get("XAI_API_KEY"):
            raise EvidenceReviewerUnavailable("xai_key_missing")

        result = agent.run_sync(
            "Normalise this Graph Recall evidence payload. Do not invent citations.\n"
            + str(payload)[:12000]
        )
        data = result.data
        out = data.model_dump()
        # Strip invented citations
        allowed_paths = {str(m.get("path") or "") for m in kitchen_memory}
        allowed_ids = {str(m.get("source_id") or "") for m in kitchen_memory}
        for srow in registered_sources:
            allowed_ids.add(str(srow.get("id") or ""))
            allowed_paths.add(str(srow.get("graph_path") or srow.get("url") or ""))
        cites = []
        for c in out.get("citations") or []:
            sid = str(c.get("source_id") or "")
            path = str(c.get("path_or_url") or "")
            if sid in allowed_ids or path in allowed_paths:
                cites.append(c)
        out["citations"] = cites
        return out, ModelMeta(provider=provider, used_ai=True, model=model_name)
    except EvidenceReviewerUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        log.info("evidence_reviewer_failed category=%s", type(e).__name__)
        raise EvidenceReviewerUnavailable(type(e).__name__) from e
