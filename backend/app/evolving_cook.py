"""Deterministic safety-first surplus/trim planner. No live LLM required."""

from __future__ import annotations

import re
from typing import Literal

from .models import (
    CookDecision,
    CookRoute,
    EvolvingCookPlan,
    EvolvingCookRequest,
    SortTray,
)

Traceability = Literal[
    "labelled_chilled_known",
    "clean_raw_trim",
    "unknown",
    "guest_exposed_buffet",
]

HIGH_RISK = frozenset(
    {
        "chicken",
        "poultry",
        "raw chicken",
        "duck",
        "turkey",
        "mince",
        "minced",
        "ground beef",
        "raw fish",
        "fish",
        "shellfish",
        "prawn",
        "shrimp",
        "oyster",
        "rice",
        "cooked rice",
        "egg",
        "eggs",
        "mayonnaise",
        "mayo",
        "cream",
        "dairy soft",
        "soft cheese",
        "gravy",
        "stock",
        "sauce",
        "stuffing",
        "paté",
        "pate",
        "liver",
        "offal",
        "sausage",
        "cured raw",
    }
)

VEG_SAFE = frozenset(
    {
        "onion",
        "carrot",
        "celery",
        "potato",
        "leek",
        "cabbage",
        "herb",
        "herbs",
        "parsley",
        "thyme",
        "garlic",
        "mushroom",
        "pepper",
        "tomato",
        "courgette",
        "zucchini",
        "trim",
        "vegetable",
        "veg",
        "greens",
        "spinach",
        "beans",
        "lentil",
        "pulse",
    }
)


def _split_items(raw: str) -> list[str]:
    parts = re.split(r"[\n,;]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _has_high_risk(items: list[str]) -> list[str]:
    hits: list[str] = []
    for it in items:
        n = _norm(it)
        for risk in HIGH_RISK:
            if risk in n or n in risk:
                hits.append(it)
                break
    return hits


def _mostly_veg(items: list[str]) -> bool:
    if not items:
        return False
    veg = 0
    for it in items:
        n = _norm(it)
        if any(v in n for v in VEG_SAFE):
            veg += 1
    return veg >= max(1, len(items) // 2)


def plan_evolving_cook(req: EvolvingCookRequest) -> EvolvingCookPlan:
    items = _split_items(req.available)
    allergens = [_norm(a) for a in _split_items(req.allergens) if a.strip()]
    outcome = (req.desired_outcome or "useful, safe staff-first use").strip()
    where = req.where_for
    trace = req.traceability

    risk_hits = _has_high_risk(items)
    guest_service_forbidden = trace in {"unknown", "guest_exposed_buffet"}

    # --- decision gate ---
    if trace == "guest_exposed_buffet":
        return _discard_plan(
            items=items,
            allergens=allergens,
            where=where,
            outcome=outcome,
            reason=(
                "Guest-exposed buffet food must never re-enter guest service. "
                "Discard, or escalate to a manager for documented disposal."
            ),
            next_step="Isolate, label DO NOT USE, log disposal time, escalate if volume is material.",
        )

    if trace == "unknown" and risk_hits:
        return _discard_plan(
            items=items,
            allergens=allergens,
            where=where,
            outcome=outcome,
            reason=(
                f"Unknown history plus higher-risk item(s): {', '.join(risk_hits)}. "
                "Do not invent a safe route — discard or escalate."
            ),
            next_step="Do not cook for anyone until a manager decides discard vs lab/test path.",
        )

    if not items:
        return EvolvingCookPlan(
            decision=CookDecision(
                verdict="caution",
                title="Nothing listed yet",
                summary="Add what is actually on the tray before planning routes.",
            ),
            do_this_next="List each trim item with where it came from and when it was produced.",
            routes=[],
            sort_tray=SortTray(
                use_now=[],
                prep_later=[],
                store=[],
                stop_or_escalate=["No items to sort — capture inventory first."],
            ),
            sensory_checks=[
                "Sight: odd colour, slime, mould",
                "Smell: sour, ammonia, rancid",
                "Feel: sticky or unusually soft",
            ],
            allergen_prompts=_allergen_prompts(allergens),
            guest_service_allowed=False,
            notes=["Deterministic safety planner — not a live model."],
        )

    if trace == "unknown":
        # lower-risk unknown still not for guest service
        decision = CookDecision(
            verdict="caution",
            title="Unknown history — staff/canteen only at best",
            summary=(
                "History is unknown. Never send this to guest service. "
                "If any doubt on smell/time/temp — discard."
            ),
        )
        next_step = "Sensory check now. If clean and clearly plant/dry goods, staff meal only; else discard."
        guest_ok = False
        classic, new, experiment = _routes_staff_only(items, where, outcome, cautious=True)
        sort = SortTray(
            use_now=[i for i in items if _mostly_veg([i])],
            prep_later=[],
            store=[],
            stop_or_escalate=[
                "Anything animal protein with unknown time/temp history",
                "Anything guest-facing was considered",
            ],
        )
    elif trace == "clean_raw_trim":
        decision = CookDecision(
            verdict="caution",
            title="Clean raw trim — cook-through path",
            summary=(
                "Treat as raw production trim: cold chain, cook thoroughly, "
                "prefer staff/canteen unless fully documented for the pass."
            ),
        )
        next_step = "Portion, chill ≤5°C, cook today or freeze labelled. Guest service only if fully traceable and menu-approved."
        guest_ok = where in {"a_la_carte", "banqueting"} and not risk_hits or (
            where in {"a_la_carte", "banqueting"} and _mostly_veg(items)
        )
        # still caution for raw animal
        if risk_hits:
            guest_ok = False
        classic, new, experiment = _routes_trim(items, where, outcome, raw=True)
        sort = SortTray(
            use_now=[i for i in items if any(x in _norm(i) for x in ("herb", "trim", "onion", "carrot"))],
            prep_later=[i for i in items if i not in []],
            store=["Label, date, chill ≤5°C — use within service window"],
            stop_or_escalate=["Any off odour or warm trim"] + ([f"High-risk: {', '.join(risk_hits)}"] if risk_hits else []),
        )
        # refine prep_later = items not use_now
        use_set = set(sort.use_now)
        sort = sort.model_copy(
            update={
                "prep_later": [i for i in items if i not in use_set][:8],
                "use_now": sort.use_now[:6] or items[:3],
            }
        )
    else:
        # labelled_chilled_known
        decision = CookDecision(
            verdict="proceed",
            title="Labelled, chilled & known — safe to plan",
            summary=(
                f"Traceable chill-chain items for {where.replace('_', ' ')}. "
                f"Aim: {outcome}."
            ),
        )
        next_step = "Confirm labels (what / when / allergen), then pick one route and execute within the labelled window."
        guest_ok = where in {"a_la_carte", "banqueting", "breakfast"} and not guest_service_forbidden
        classic, new, experiment = _routes_known(items, where, outcome)
        sort = SortTray(
            use_now=items[:3],
            prep_later=items[3:6],
            store=["Keep labelled ≤5°C", "FIFO the oldest first"],
            stop_or_escalate=["Past use-by", "Broken chill chain", "Label missing allergens"],
        )

    if guest_service_forbidden:
        guest_ok = False
        classic = classic.model_copy(
            update={
                "guest_service": False,
                "notes": list(classic.notes) + ["Not for guest service."],
            }
        )
        new = new.model_copy(update={"guest_service": False})
        experiment = experiment.model_copy(update={"guest_service": False})

    return EvolvingCookPlan(
        decision=decision,
        do_this_next=next_step,
        routes=[classic, new, experiment],
        sort_tray=sort,
        sensory_checks=[
            "Sight: colour, dryness, mould, packaging integrity",
            "Smell: clean vs sour / ammonia / rancid",
            "Feel: slimy or sticky surfaces → stop",
            "Time/temp: still within labelled chill window?",
        ],
        allergen_prompts=_allergen_prompts(allergens),
        guest_service_allowed=guest_ok and not guest_service_forbidden,
        notes=[
            "Unknown or guest-exposed food is never suggested for guest service.",
            "Deterministic safety planner — no live AI provider claimed.",
        ],
        available_items=items,
    )


def _allergen_prompts(allergens: list[str]) -> list[str]:
    base = [
        "Carry forward every allergen onto the new dish label before it leaves the pass.",
        "If allergens are incomplete, treat as may-contain until verified.",
    ]
    if not allergens:
        return base + ["No allergens listed — confirm with production label, do not assume free-from."]
    named = ", ".join(allergens)
    return base + [
        f"Declared to carry forward: {named}.",
        "Update allergen matrix / pass board if this becomes a special or staff meal.",
        "Cross-contact: shared boards, fryers, and tongs still transfer allergens.",
    ]


def _discard_plan(
    *,
    items: list[str],
    allergens: list[str],
    where: str,
    outcome: str,
    reason: str,
    next_step: str,
) -> EvolvingCookPlan:
    return EvolvingCookPlan(
        decision=CookDecision(
            verdict="discard_or_escalate",
            title="Discard or escalate",
            summary=reason,
        ),
        do_this_next=next_step,
        routes=[
            CookRoute(
                id="classic",
                title="Classic route",
                summary="No cook-forward classic path — safety stop.",
                steps=["Do not rework into guest dishes.", "Document disposal."],
                guest_service=False,
            ),
            CookRoute(
                id="new",
                title="New direction",
                summary="No creative rework until a manager signs off disposal.",
                steps=["Photograph / log if policy requires.", "Escalate volume > small tray."],
                guest_service=False,
            ),
            CookRoute(
                id="experiment",
                title="Small experiment",
                summary="Experiments are closed on this tray.",
                steps=["Do not taste-test questionable protein.", "Clean the container thoroughly."],
                guest_service=False,
            ),
        ],
        sort_tray=SortTray(
            use_now=[],
            prep_later=[],
            store=[],
            stop_or_escalate=items or ["Entire tray"],
        ),
        sensory_checks=[
            "Do not rely on sensory alone for high-risk or guest-exposed product.",
            "If already warm or odorous — discard immediately.",
        ],
        allergen_prompts=_allergen_prompts(allergens),
        guest_service_allowed=False,
        notes=[
            f"Where requested: {where}. Outcome ignored for safety: {outcome}.",
            "Unknown or guest-exposed food must never be suggested for guest service.",
        ],
        available_items=items,
    )


def _routes_known(items: list[str], where: str, outcome: str) -> tuple[CookRoute, CookRoute, CookRoute]:
    joined = ", ".join(items[:6]) or "surplus"
    classic = CookRoute(
        id="classic",
        title="Classic route",
        summary=f"Straightforward cook for {where.replace('_', ' ')} using {joined}.",
        steps=[
            "Check labels and allergens.",
            "Reheat/cook to safe core temp if previously cooked.",
            f"Finish toward: {outcome}.",
            "Serve within the same service window.",
        ],
        guest_service=where in {"a_la_carte", "banqueting", "breakfast"},
    )
    new = CookRoute(
        id="new",
        title="New direction",
        summary="Reframe as a single composed special or staff board dish.",
        steps=[
            "Pick one hero item; support with two sides from the tray.",
            "One sauce only — avoid stacking leftovers.",
            "Name it clearly on the board with allergens.",
        ],
        guest_service=where in {"a_la_carte", "banqueting"},
    )
    experiment = CookRoute(
        id="experiment",
        title="Small experiment",
        summary="Half-tray trial — not a full service commitment.",
        steps=[
            "Cook a 4–6 portion test only.",
            "Taste, temp, and allergen check before scaling.",
            "If good, promote to classic route next service.",
        ],
        guest_service=False,
        notes=["Keep experiments staff-facing until signed off."],
    )
    return classic, new, experiment


def _routes_trim(
    items: list[str], where: str, outcome: str, *, raw: bool
) -> tuple[CookRoute, CookRoute, CookRoute]:
    joined = ", ".join(items[:6]) or "trim"
    classic = CookRoute(
        id="classic",
        title="Classic route",
        summary=f"Stock / soffritto / cooked mince path for {joined}." if raw else f"Use {joined} promptly.",
        steps=[
            "Keep raw separate from ready-to-eat.",
            "Cook thoroughly; chill fast if not serving now.",
            f"Target: {outcome}.",
        ],
        guest_service=False if raw else where in {"canteen", "staff_meal", "home"},
    )
    new = CookRoute(
        id="new",
        title="New direction",
        summary="Turn trim into a defined staff or breakfast component.",
        steps=[
            "Batch cook, label with date/time/allergen.",
            "Use as filling, hash base, or sauce foundation.",
        ],
        guest_service=False,
    )
    experiment = CookRoute(
        id="experiment",
        title="Small experiment",
        summary="One-pan test cook from the smallest trim pile.",
        steps=["Cook small, cool correctly, decide keep vs discard.", "No guest plate from this test."],
        guest_service=False,
    )
    return classic, new, experiment


def _routes_staff_only(
    items: list[str], where: str, outcome: str, *, cautious: bool
) -> tuple[CookRoute, CookRoute, CookRoute]:
    joined = ", ".join(items[:5]) or "items"
    classic = CookRoute(
        id="classic",
        title="Classic route",
        summary=f"Staff/canteen only for {joined}." + (" High caution." if cautious else ""),
        steps=[
            "Sensory check; discard on doubt.",
            "Cook thoroughly; serve staff only.",
            f"Outcome: {outcome} (non-guest).",
        ],
        guest_service=False,
    )
    new = CookRoute(
        id="new",
        title="New direction",
        summary="Simple staff board — one pot, clear label.",
        steps=["Avoid multi-day holds.", "Eat same day."],
        guest_service=False,
    )
    experiment = CookRoute(
        id="experiment",
        title="Small experiment",
        summary="Not recommended when history is thin — skip unless plant-only and clean.",
        steps=["If unsure, choose discard instead of experiment."],
        guest_service=False,
    )
    return classic, new, experiment
