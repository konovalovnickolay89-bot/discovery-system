"""Local Cook Studio planning by mode. Safety is local-first; never overridden by Kitchen memory."""

from __future__ import annotations

from .evolving_cook import plan_evolving_cook
from .kitchen_models import (
    CookConsultation,
    CookConsultationCreate,
    CookMode,
    CookStudioPlan,
    CookTaskStatus,
    GraphRecallStatus,
    KitchenMemoryItem,
    RecipeSpineFull,
    ServiceContext,
    TraceabilityStatus,
)
from .kitchen_repo import (
    get_dish,
    get_ingredient,
    get_produce,
    list_active_consultations,
    new_consultation_id,
    save_consultation,
)
from .models import EvolvingCookRequest, EvolvingCookTraceability, EvolvingCookWhere
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _map_where(ctx: ServiceContext) -> EvolvingCookWhere:
    m = {
        ServiceContext.canteen: EvolvingCookWhere.canteen,
        ServiceContext.staff_meal: EvolvingCookWhere.staff_meal,
        ServiceContext.breakfast: EvolvingCookWhere.breakfast,
        ServiceContext.banqueting: EvolvingCookWhere.banqueting,
        ServiceContext.a_la_carte: EvolvingCookWhere.a_la_carte,
        ServiceContext.home: EvolvingCookWhere.home,
        ServiceContext.undecided: EvolvingCookWhere.undecided,
        ServiceContext.pass_station: EvolvingCookWhere.a_la_carte,
    }
    return m.get(ctx, EvolvingCookWhere.undecided)


def _map_trace(t: TraceabilityStatus) -> EvolvingCookTraceability:
    return EvolvingCookTraceability(t.value)


def _title_for(body: CookConsultationCreate) -> str:
    if body.title.strip():
        return body.title.strip()[:80]
    raw = (body.ingredients_or_problem or "").strip().split("\n")[0][:48]
    return f"{body.mode.value} · {raw or 'task'}"


def build_local_plan(body: CookConsultationCreate) -> CookStudioPlan:
    """Mode-aware local plan. Rescue uses strict evolving-cook safety."""
    # resolve lot names into available text
    parts = [body.ingredients_or_problem.strip()] if body.ingredients_or_problem.strip() else []
    for lid in body.produce_lot_ids:
        lot = get_produce(lid)
        if lot:
            parts.append(f"{lot.name} ({lot.quantity}{lot.unit})")
    for iid in body.ingredient_ids:
        ing = get_ingredient(iid)
        if ing:
            parts.append(ing.name)
    available = ", ".join(p for p in parts if p) or body.ingredients_or_problem
    allergens = ", ".join(body.allergens)

    # Always run safety kernel (evolving cook) for food risk gates
    ec = plan_evolving_cook(
        EvolvingCookRequest(
            available=available,
            traceability=_map_trace(body.traceability),
            where_for=_map_where(body.service_context),
            allergens=allergens,
            desired_outcome=body.desired_outcome or body.mode.value,
        )
    )

    rejected = ec.decision.verdict == "discard_or_escalate"
    guest_ok = bool(ec.guest_service_allowed) and not rejected

    if rejected:
        return CookStudioPlan(
            decision={
                "verdict": "discard_or_escalate",
                "title": ec.decision.title,
                "summary": ec.decision.summary,
            },
            recommended_action=ec.do_this_next,
            primary_plan={},
            alternatives=[],
            recipe_spine=RecipeSpineFull(),
            allergen_checks=ec.allergen_prompts,
            service_checks=["Do not return this product to guest service."],
            disposal_checklist=[
                "Isolate tray / label DO NOT USE",
                "Log time and reason",
                "Dispose per site policy or escalate manager",
                "Sanitise container and surface",
                "Update produce lot status to waste/quarantined if linked",
            ]
            + list(ec.sort_tray.stop_or_escalate),
            kitchen_memory=[],
            guest_service_allowed=False,
            rejected=True,
            notes=list(ec.notes)
            + ["Local safety decision — Kitchen memory cannot override this."],
        )

    # Mode-shaped professional output
    routes = ec.routes
    primary = routes[0] if routes else None
    alts = routes[1:3] if len(routes) > 1 else []

    if body.mode == CookMode.build:
        purpose = f"Build a dish/component for {body.service_context.value} from: {available}"
        method = " · ".join(primary.steps) if primary else "Define mise, cook, hold, finish."
        primary_plan = {
            "title": primary.title if primary else "Primary build",
            "summary": primary.summary if primary else "",
            "steps": primary.steps if primary else [],
            "contract": "strategic_application",
        }
        alts_out = [
            {
                "title": a.title,
                "summary": a.summary,
                "steps": a.steps,
                "contract": "strategic_application",
            }
            for a in alts
        ]
        spine = RecipeSpineFull(
            purpose=purpose,
            mise=f"Gather: {available}. Allergens: {allergens or 'verify labels'}.",
            method=method,
            holding_regeneration="Hold hot ≥63°C or chill ≤5°C within 90 minutes of cook.",
            pass_finish="Plate clean; announce allergens on pass.",
            failure_recovery="If undercooked/out of temp — rework or discard; do not plate.",
        )
    elif body.mode == CookMode.rescue:
        primary_plan = {
            "title": primary.title if primary else "Rescue path",
            "summary": primary.summary if primary else "",
            "steps": primary.steps if primary else [],
            "contract": "strategic_application_strict_safety",
        }
        alts_out = [
            {"title": a.title, "summary": a.summary, "steps": a.steps, "contract": "strict_safety"}
            for a in alts
        ]
        spine = RecipeSpineFull(
            purpose=f"Rescue surplus/trim safely for {body.service_context.value}",
            mise="Sort tray: use now / prep later / store / stop.",
            method=" · ".join(primary.steps) if primary else "Cook-through or discard.",
            holding_regeneration="Label date/time; no multi-day holds on unknown product.",
            pass_finish="Staff/canteen preferred unless fully traceable.",
            failure_recovery="Any sensory fail → disposal checklist.",
        )
    elif body.mode == CookMode.service:
        primary_plan = {
            "title": "Service triage",
            "summary": body.ingredients_or_problem or "Live pass issue",
            "steps": [
                "Stabilize the pass: time, temperature, allergen call.",
                primary.summary if primary else "Choose one recovery action.",
                "Communicate to floor once with ETA.",
            ],
            "contract": "strategic_application",
        }
        alts_out = [
            {"title": "Re-fire path", "summary": "Remake critical component only.", "steps": ["Isolate bad plate", "Re-fire clean"]},
            {"title": "86 / sub path", "summary": "Strike and offer equal-path substitute.", "steps": ["Board strike", "Floor brief"]},
        ]
        spine = RecipeSpineFull(
            purpose="Recover live service without compounding risk",
            mise="What is on the pass now; what is 86'd.",
            method=primary_plan["steps"][0] if primary_plan["steps"] else "",
            holding_regeneration="Do not hold compromised product.",
            pass_finish="Guest recovery language; allergen re-check.",
            failure_recovery="Escalate manager if guest complaint or allergen event.",
        )
    else:  # develop
        primary_plan = {
            "title": "Develop — option set (max 3)",
            "summary": body.desired_outcome or "Improve dish",
            "steps": ["Define current dish weakness", "Change one variable", "Taste and cost check"],
            "contract": "creative_layer_max_3",
        }
        alts_out = [
            {"title": "Flavour pivot", "summary": "One acid/heat/fat change only.", "steps": ["A/B taste 2 portions"]},
            {"title": "Cost / yield pivot", "summary": "Trim waste or swap garnish cost.", "steps": ["Cost both plates"]},
            {"title": "Allergen version", "summary": "Controlled free-from variant.", "steps": ["Separate mise", "Relabel"]},
        ][:3]
        spine = RecipeSpineFull(
            purpose=f"Develop: {body.desired_outcome or available}",
            mise="Baseline dish + change set (≤3 options).",
            method="Run controlled trials; log winner.",
            holding_regeneration="As current dish SOP.",
            pass_finish="Document plating change once.",
            failure_recovery="Revert to approved version if trial fails.",
        )

    return CookStudioPlan(
        decision={
            "verdict": ec.decision.verdict if ec.decision.verdict != "discard_or_escalate" else "caution",
            "title": ec.decision.title,
            "summary": ec.decision.summary,
        },
        recommended_action=ec.do_this_next,
        primary_plan=primary_plan,
        alternatives=alts_out,
        recipe_spine=spine,
        allergen_checks=ec.allergen_prompts,
        service_checks=[
            f"Context: {body.service_context.value}",
            f"Guest service allowed by local safety: {'yes' if guest_ok else 'no'}",
            f"Portions: {body.covers_or_portions or '—'}",
            f"Time window: {body.time_available_minutes or '—'} min",
            f"Equipment: {', '.join(body.equipment) or '—'}",
        ],
        disposal_checklist=[],
        kitchen_memory=[],
        guest_service_allowed=guest_ok,
        rejected=False,
        notes=[
            "Local plan only until Kitchen memory returns.",
            "Kitchen memory may enrich, never override safety.",
            "Database Expansion is never automatic.",
        ],
    )


def create_consultation(body: CookConsultationCreate, *, actor: str = "session") -> CookConsultation:
    from .graph_recall_queue import enqueue_graph_recall

    now = _now()
    plan = build_local_plan(body)
    rejected = plan.rejected

    if rejected:
        task = CookTaskStatus.blocked
        gr = GraphRecallStatus.not_requested
    else:
        task = CookTaskStatus.local_plan_ready
        gr = (
            GraphRecallStatus.queued
            if body.request_graph_recall
            else GraphRecallStatus.not_requested
        )
        if gr == GraphRecallStatus.queued:
            task = CookTaskStatus.kitchen_memory_queued

    c = CookConsultation(
        id=new_consultation_id(),
        mode=body.mode,
        title=_title_for(body),
        ingredients_or_problem=body.ingredients_or_problem,
        produce_lot_ids=body.produce_lot_ids,
        ingredient_ids=body.ingredient_ids,
        dish_id=body.dish_id,
        traceability=body.traceability,
        service_context=body.service_context,
        allergens=body.allergens,
        covers_or_portions=body.covers_or_portions,
        time_available_minutes=body.time_available_minutes,
        equipment=body.equipment,
        desired_outcome=body.desired_outcome,
        local_safety_plan=plan,
        graph_recall_status=gr,
        graph_recall_response=None,
        task_status=task,
        audit=[
            {"at": now.isoformat(), "event": "created", "actor": actor},
            {"at": now.isoformat(), "event": "safety_checked", "verdict": plan.decision.get("verdict")},
            {"at": now.isoformat(), "event": "local_plan_ready" if not rejected else "blocked"},
        ],
        created_at=now,
        updated_at=now,
        blocked_reason=plan.decision.get("summary") if rejected else None,
    )
    save_consultation(c)

    if gr == GraphRecallStatus.queued:
        enqueue_graph_recall(c)

    return c


def merge_kitchen_memory(
    c: CookConsultation,
    memory: list[dict],
    enrichment: dict,
    *,
    proposed_guest_service: bool | None,
    research_status: str | None = None,
    research_pending_ids: list[str] | None = None,
    sources_conflict: bool = False,
    structurer=None,
) -> CookConsultation:
    """Apply Graph Recall enrichment + evidence gate without overriding local safety."""
    from .evidence_gate import apply_evidence_gate_to_consultation
    from .evidence_models import ResearchStatus
    from .research import fetch_research_pending

    plan = c.local_safety_plan
    if isinstance(plan, dict):
        plan = CookStudioPlan.model_validate(plan)
    else:
        plan = plan.model_copy(deep=True)

    items = [
        KitchenMemoryItem(
            title=str(m.get("title") or "source"),
            path=str(m.get("path") or ""),
            relevance=str(m.get("relevance") or ""),
            excerpt=str(m.get("excerpt") or ""),
            source_id=str(m.get("source_id") or ""),
            authority_tier=m.get("authority_tier"),
        )
        for m in memory
    ]
    plan.kitchen_memory = items

    if plan.rejected:
        plan.notes = list(plan.notes) + [
            "Kitchen memory ignored for creative routes — task remains blocked by local safety."
        ]
        if proposed_guest_service:
            plan.notes.append("Worker proposed guest service — rejected by local safety.")
    else:
        if enrichment.get("primary_plan") and isinstance(enrichment["primary_plan"], dict):
            base = dict(plan.primary_plan)
            base["kitchen_memory_note"] = enrichment["primary_plan"].get("summary") or enrichment.get(
                "note"
            )
            plan.primary_plan = base
        if proposed_guest_service is True and not plan.guest_service_allowed:
            plan.notes = list(plan.notes) + [
                "Kitchen memory suggested guest service — kept blocked by local safety."
            ]
        plan.notes = list(plan.notes) + ["Kitchen memory applied as enrichment only."]

    rs = ResearchStatus.not_needed
    pending_ids = list(research_pending_ids or [])
    if research_status:
        try:
            rs = ResearchStatus(research_status)
        except Exception:  # noqa: BLE001
            rs = ResearchStatus.not_needed

    if not plan.rejected and not memory and not pending_ids:
        try:
            rs2, pids, _findings = fetch_research_pending(
                c.ingredients_or_problem or c.title,
                consultation_id=c.id,
            )
            if pids:
                rs = rs2
                pending_ids = pids
                plan.notes = list(plan.notes) + [
                    "Research findings saved as pending_review — not auto-canonical."
                ]
        except Exception:  # noqa: BLE001
            pass

    rec = plan.recommended_action or enrichment.get("note") or ""
    verdict = str((plan.decision or {}).get("verdict") or "unknown")
    gated = apply_evidence_gate_to_consultation(
        c.id,
        kitchen_memory=[m.model_dump() for m in items],
        enrichment=enrichment or {},
        recommendation=rec,
        safety_verdict=verdict,
        local_blocked=bool(plan.rejected),
        research_status=rs,
        research_pending_ids=pending_ids,
        structurer=structurer,
        sources_conflict=sources_conflict,
    )

    tiers = [int(ci.authority_tier.value) for ci in gated.citations]
    plan.evidence_source_count = len(gated.citations)
    plan.evidence_best_tier = min(tiers) if tiers else None
    plan.evidence_gate_status = gated.gate_status.value
    plan.evidence_research_status = gated.research_status.value
    plan.evidence_verified = bool(gated.verified_for_professional_use)
    plan.evidence_unknowns = list(gated.unknowns_or_conflicts)
    plan.evidence_citations = [ci.model_dump(mode="json") for ci in gated.citations]

    if not gated.verified_for_professional_use and not plan.rejected:
        plan.notes = list(plan.notes) + [
            "Not a verified professional recommendation — insufficient evidence or pending review."
        ]

    if gated.citations:
        by_path = {ci.path_or_url: ci for ci in gated.citations}
        new_items = []
        for m in items:
            ci = by_path.get(m.path)
            if ci:
                new_items.append(
                    m.model_copy(
                        update={
                            "source_id": ci.source_id,
                            "authority_tier": int(ci.authority_tier.value),
                        }
                    )
                )
            else:
                new_items.append(m)
        plan.kitchen_memory = new_items

    now = _now()
    c = c.model_copy(
        update={
            "local_safety_plan": plan,
            "graph_recall_status": GraphRecallStatus.completed,
            "graph_recall_response": {
                "kitchen_memory": memory,
                "enrichment": enrichment,
                "evidence_gate": gated.model_dump(mode="json"),
            },
            "evidence_bundle": {
                "gate_status": gated.gate_status.value,
                "research_status": gated.research_status.value,
                "verified": gated.verified_for_professional_use,
                "source_count": plan.evidence_source_count,
                "best_tier": plan.evidence_best_tier,
            },
            "task_status": CookTaskStatus.blocked
            if plan.rejected
            else CookTaskStatus.kitchen_memory_returned,
            "updated_at": now,
            "audit": list(c.audit)
            + [
                {
                    "at": now.isoformat(),
                    "event": "kitchen_memory_returned",
                    "gate_status": gated.gate_status.value,
                    "verified": gated.verified_for_professional_use,
                }
            ],
        }
    )
    return save_consultation(c)




def active_task_snapshot() -> list[dict]:
    out = []
    for c in list_active_consultations()[:8]:
        plan = c.local_safety_plan
        verdict = ""
        if isinstance(plan, dict):
            verdict = (plan.get("decision") or {}).get("verdict", "")
        else:
            verdict = plan.decision.get("verdict", "")
        out.append(
            {
                "id": c.id,
                "mode": c.mode.value,
                "title": c.title,
                "task_status": c.task_status.value,
                "graph_recall_status": c.graph_recall_status.value,
                "safety_verdict": verdict,
                "blocked_reason": c.blocked_reason,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
        )
    return out
