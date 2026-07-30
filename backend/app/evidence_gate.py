"""PydanticAI structures an answer; Pydantic + registry validate evidence. Not truth itself."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from pydantic import ValidationError

from .evidence_models import (
    SAFETY_CLAIM_MARKERS,
    AuthorityTier,
    EvidenceGateStatus,
    EvidenceGatedResult,
    ModelMeta,
    ResearchStatus,
)
from .evidence_store import (
    citation_from_source,
    ensure_source_for_graph_hit,
    get_source,
    is_approved_graph_path,
    is_legacy_local_path,
    link_consultation_evidence,
    list_evidence_for_consultation,
)

log = logging.getLogger("casual_board.evidence_gate")

# Injectable structured generator for tests (fake PydanticAI)
EvidenceStructurerFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def _text_has_safety_claim(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in SAFETY_CLAIM_MARKERS)


def _has_tier1(citations: list) -> bool:
    for c in citations:
        tier = c.authority_tier if hasattr(c, "authority_tier") else c.get("authority_tier")
        if isinstance(tier, AuthorityTier):
            if tier == AuthorityTier.tier_1_official:
                return True
        elif int(tier) == 1:
            return True
    return False


def structure_with_pydantic_ai(
    *,
    recommendation: str,
    safety_verdict: str,
    kitchen_memory: list[dict[str, Any]],
    enrichment: dict[str, Any],
    consultation_id: str,
    local_blocked: bool,
    structurer: EvidenceStructurerFn | None = None,
) -> tuple[dict[str, Any], ModelMeta]:
    """
    Produce a structured draft. used_ai True only for live provider success.
    Default uses deterministic function model (no network).
    """
    meta = ModelMeta(provider="function", used_ai=False, model="evidence-function")

    def _default(prompt: str, ctx: dict[str, Any]) -> dict[str, Any]:
        mem = ctx.get("kitchen_memory") or []
        cites = []
        for m in mem:
            cites.append(
                {
                    "source_id": m.get("source_id") or "",
                    "title": m.get("title") or "note",
                    "path_or_url": m.get("path") or m.get("path_or_url") or "",
                    "excerpt": m.get("excerpt") or m.get("finding") or "",
                    "authority_tier": m.get("authority_tier") or 2,
                }
            )
        conf = 0.55 if cites else 0.15
        return {
            "recommendation": ctx.get("recommendation") or "",
            "safety_verdict": ctx.get("safety_verdict") or "unknown",
            "citations": cites,
            "confidence": conf,
            "unknowns_or_conflicts": ctx.get("unknowns") or [],
            "research_status": "not_needed",
        }

    ctx = {
        "recommendation": recommendation,
        "safety_verdict": safety_verdict,
        "kitchen_memory": kitchen_memory,
        "enrichment": enrichment,
        "local_blocked": local_blocked,
        "unknowns": list(enrichment.get("unknowns") or []),
    }
    prompt = f"Structure evidence-gated culinary answer for {consultation_id}"

    if structurer is not None:
        raw = structurer(prompt, ctx)
        meta = ModelMeta(provider="test", used_ai=False, model="fake")
        return raw, meta

    # Optional live PydanticAI — function model by default
    try:
        from .config import get_settings

        settings = get_settings()
        if settings.enable_pydantic_ai and settings.resolved_ai_provider() in {"openai", "xai"}:
            # Live path reserved; still structure via deterministic for safety without network in tests
            pass
    except Exception:  # noqa: BLE001
        pass

    raw = _default(prompt, ctx)
    return raw, meta


def register_memory_as_evidence(
    kitchen_memory: list[dict[str, Any]],
    *,
    consultation_id: str,
) -> list[dict[str, Any]]:
    """Attach registry source_id / tier to each memory item; drop bad paths."""
    out: list[dict[str, Any]] = []
    for m in kitchen_memory or []:
        title = str(m.get("title") or "note")
        path = str(m.get("path") or "")
        excerpt = str(m.get("excerpt") or m.get("finding") or "")
        if is_legacy_local_path(path):
            src, ev = ensure_source_for_graph_hit(
                title=title, path=path, excerpt=excerpt, consultation_id=consultation_id
            )
            # legacy — not usable as professional citation for safety
            out.append(
                {
                    "title": title,
                    "path": "",
                    "excerpt": excerpt,
                    "relevance": m.get("relevance") or "legacy_unverified",
                    "source_id": src.id if src else "",
                    "authority_tier": 5,
                    "evidence_id": ev.id if ev else None,
                    "unverified_legacy": True,
                }
            )
            continue
        if path and not is_approved_graph_path(path):
            continue  # unsupported path
        src, ev = ensure_source_for_graph_hit(
            title=title, path=path, excerpt=excerpt, consultation_id=consultation_id
        )
        if not src:
            continue
        out.append(
            {
                "title": title,
                "path": path,
                "excerpt": excerpt,
                "relevance": m.get("relevance") or "",
                "source_id": src.id,
                "authority_tier": int(src.authority_tier.value),
                "evidence_id": ev.id if ev else None,
            }
        )
    return out


def validate_gated_result(
    raw: dict[str, Any],
    *,
    kitchen_memory_registered: list[dict[str, Any]],
    local_blocked: bool,
    research_status: ResearchStatus = ResearchStatus.not_needed,
    model_meta: ModelMeta | None = None,
    disclose_conflicts: bool | None = None,
) -> EvidenceGatedResult:
    """Reject/downgrade when evidence rules fail. Blocked local safety always wins."""
    if local_blocked:
        return EvidenceGatedResult(
            recommendation=str(raw.get("recommendation") or "Blocked by local safety"),
            safety_verdict="blocked",
            citations=[],
            confidence=0.0,
            unknowns_or_conflicts=["Local safety blocked — Graph Recall/research cannot unblock"],
            research_status=research_status,
            gate_status=EvidenceGateStatus.blocked_local_safety,
            model_meta=model_meta or ModelMeta(),
            verified_for_professional_use=False,
        )

    # Resolve citations against registry
    resolved = []
    unresolved = []
    for c in raw.get("citations") or []:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("source_id") or "")
        path = str(c.get("path_or_url") or c.get("path") or "")
        if is_legacy_local_path(path):
            unresolved.append(f"legacy path not canonical: {path[:80]}")
            continue
        src = get_source(sid) if sid else None
        if not src and path:
            # try match registered memory
            for m in kitchen_memory_registered:
                if m.get("path") == path and m.get("source_id"):
                    src = get_source(m["source_id"])
                    sid = m["source_id"]
                    break
        if not src:
            unresolved.append(f"unresolved citation: {c.get('title') or path or sid}")
            continue
        if not src.active:
            unresolved.append(f"inactive source: {src.id}")
            continue
        resolved.append(
            citation_from_source(
                src,
                excerpt=str(c.get("excerpt") or ""),
                evidence_id=c.get("evidence_id") or next(
                    (m.get("evidence_id") for m in kitchen_memory_registered if m.get("source_id") == src.id),
                    None,
                ),
            )
        )

    # Also promote registered memory as citations if model omitted them
    if not resolved and kitchen_memory_registered:
        for m in kitchen_memory_registered:
            if m.get("unverified_legacy"):
                continue
            src = get_source(m["source_id"]) if m.get("source_id") else None
            if src and src.active:
                resolved.append(
                    citation_from_source(src, excerpt=m.get("excerpt") or "", evidence_id=m.get("evidence_id"))
                )

    rec = str(raw.get("recommendation") or "").strip()
    verdict = str(raw.get("safety_verdict") or "unknown").strip()
    unknowns = [str(u) for u in (raw.get("unknowns_or_conflicts") or [])]
    unknowns.extend(unresolved)

    # Conflict disclosure: if multiple tiers disagree on safety language
    safety_text = f"{rec} {verdict}".lower()
    has_safety = _text_has_safety_claim(rec) or _text_has_safety_claim(verdict) or _text_has_safety_claim(
        str(raw.get("claims") or "")
    )

    # Force conflict flag if caller reports conflict without disclosure
    conflicts_flag = bool(raw.get("sources_conflict"))
    if conflicts_flag and not any("conflict" in u.lower() for u in unknowns):
        unknowns.append("sources conflict — result did not disclose conflict")
        return EvidenceGatedResult(
            recommendation=rec or "Insufficient evidence",
            safety_verdict=verdict,
            citations=resolved,
            confidence=min(0.3, float(raw.get("confidence") or 0)),
            unknowns_or_conflicts=unknowns,
            research_status=research_status,
            gate_status=EvidenceGateStatus.insufficient_evidence,
            model_meta=model_meta or ModelMeta(),
            verified_for_professional_use=False,
        )

    if has_safety and not _has_tier1(resolved):
        unknowns.append("safety/allergen/storage/temperature/legal claim lacks Tier 1 citation")
        return EvidenceGatedResult(
            recommendation=rec or "Insufficient evidence for safety claim",
            safety_verdict=verdict,
            citations=resolved,
            confidence=min(0.25, float(raw.get("confidence") or 0)),
            unknowns_or_conflicts=unknowns,
            research_status=research_status
            if research_status != ResearchStatus.not_needed
            else ResearchStatus.pending_review,
            gate_status=EvidenceGateStatus.insufficient_evidence,
            model_meta=model_meta or ModelMeta(),
            verified_for_professional_use=False,
        )

    if not resolved:
        return EvidenceGatedResult(
            recommendation=rec or "Insufficient evidence",
            safety_verdict=verdict,
            citations=[],
            confidence=min(0.2, float(raw.get("confidence") or 0)),
            unknowns_or_conflicts=unknowns + ["no resolvable citations"],
            research_status=research_status,
            gate_status=EvidenceGateStatus.insufficient_evidence,
            model_meta=model_meta or ModelMeta(),
            verified_for_professional_use=False,
        )

    try:
        conf = float(raw.get("confidence") or 0.5)
    except (TypeError, ValueError):
        conf = 0.5

    rs = research_status
    try:
        if raw.get("research_status"):
            rs = ResearchStatus(str(raw["research_status"]))
    except Exception:  # noqa: BLE001
        pass

    gate = EvidenceGateStatus.verified
    if rs == ResearchStatus.pending_review:
        gate = EvidenceGateStatus.pending_review

    return EvidenceGatedResult(
        recommendation=rec,
        safety_verdict=verdict,
        citations=resolved,
        confidence=conf,
        unknowns_or_conflicts=unknowns,
        research_status=rs,
        gate_status=gate,
        model_meta=model_meta or ModelMeta(),
        verified_for_professional_use=gate == EvidenceGateStatus.verified and conf >= 0.4,
    )


def apply_evidence_gate_to_consultation(
    consultation_id: str,
    *,
    kitchen_memory: list[dict[str, Any]],
    enrichment: dict[str, Any],
    recommendation: str,
    safety_verdict: str,
    local_blocked: bool,
    research_status: ResearchStatus = ResearchStatus.not_needed,
    research_pending_ids: list[str] | None = None,
    structurer: EvidenceStructurerFn | None = None,
    sources_conflict: bool = False,
) -> EvidenceGatedResult:
    registered = register_memory_as_evidence(kitchen_memory, consultation_id=consultation_id)
    raw, meta = structure_with_pydantic_ai(
        recommendation=recommendation,
        safety_verdict=safety_verdict,
        kitchen_memory=registered,
        enrichment=enrichment,
        consultation_id=consultation_id,
        local_blocked=local_blocked,
        structurer=structurer,
    )
    if sources_conflict:
        raw = {**raw, "sources_conflict": True}
    result = validate_gated_result(
        raw,
        kitchen_memory_registered=registered,
        local_blocked=local_blocked,
        research_status=research_status,
        model_meta=meta,
    )
    eids = [m["evidence_id"] for m in registered if m.get("evidence_id")]
    sids = list({m["source_id"] for m in registered if m.get("source_id")})
    for c in result.citations:
        if c.source_id not in sids:
            sids.append(c.source_id)
        if c.evidence_id and c.evidence_id not in eids:
            eids.append(c.evidence_id)
    link_consultation_evidence(
        consultation_id,
        evidence_ids=eids,
        source_ids=sids,
        gated_result=result.model_dump(mode="json"),
        research_pending_ids=research_pending_ids or [],
    )
    return result
