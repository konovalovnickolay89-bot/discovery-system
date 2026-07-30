"""Cook Studio REST routes — kitchen library + consultations + Graph Recall + sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_graph_recall
from .cook_studio import create_consultation
from .evidence_models import CanonicalSource, CanonicalSourceCreate, SourceEvidence
from .evidence_store import (
    create_source,
    get_consultation_evidence,
    list_evidence_for_consultation,
    list_sources,
    seed_official_fsa_placeholder,
)
from .graph_recall_queue import complete_result, long_poll_lease, reap_expired_leases
from .kitchen_models import (
    CookConsultation,
    CookConsultationCreate,
    CookTaskStatus,
    Dish,
    DishCreate,
    DishType,
    GraphRecallLeaseResponse,
    GraphRecallResultRequest,
    Ingredient,
    IngredientCreate,
    ProduceLot,
    ProduceLotCreate,
    RecipeSpineFull,
    SaveDishFromConsultation,
)
from .kitchen_repo import (
    create_dish,
    create_ingredient,
    create_produce,
    delete_dish,
    delete_ingredient,
    delete_produce,
    get_consultation,
    get_dish,
    list_active_consultations,
    list_consultations,
    list_dishes,
    list_ingredients,
    list_produce,
    save_consultation,
    update_dish,
    update_ingredient,
    update_produce,
)
from .sessions import require_session

router = APIRouter(tags=["cook-studio"])


# --- produce ---
@router.get("/v1/kitchen/produce", response_model=list[ProduceLot])
def api_list_produce(_s: dict = Depends(require_session)):
    return list_produce()


@router.post("/v1/kitchen/produce", response_model=ProduceLot)
def api_create_produce(body: ProduceLotCreate, _s: dict = Depends(require_session)):
    return create_produce(body)


@router.put("/v1/kitchen/produce/{lot_id}", response_model=ProduceLot)
def api_update_produce(lot_id: str, body: ProduceLotCreate, _s: dict = Depends(require_session)):
    return update_produce(lot_id, body)


@router.delete("/v1/kitchen/produce/{lot_id}")
def api_delete_produce(lot_id: str, _s: dict = Depends(require_session)):
    delete_produce(lot_id)
    return {"ok": True}


# --- ingredients ---
@router.get("/v1/kitchen/ingredients", response_model=list[Ingredient])
def api_list_ingredients(_s: dict = Depends(require_session)):
    return list_ingredients()


@router.post("/v1/kitchen/ingredients", response_model=Ingredient)
def api_create_ingredient(body: IngredientCreate, _s: dict = Depends(require_session)):
    return create_ingredient(body)


@router.put("/v1/kitchen/ingredients/{ing_id}", response_model=Ingredient)
def api_update_ingredient(ing_id: str, body: IngredientCreate, _s: dict = Depends(require_session)):
    return update_ingredient(ing_id, body)


@router.delete("/v1/kitchen/ingredients/{ing_id}")
def api_delete_ingredient(ing_id: str, _s: dict = Depends(require_session)):
    delete_ingredient(ing_id)
    return {"ok": True}


# --- dishes ---
@router.get("/v1/kitchen/dishes", response_model=list[Dish])
def api_list_dishes(_s: dict = Depends(require_session)):
    return list_dishes()


@router.post("/v1/kitchen/dishes", response_model=Dish)
def api_create_dish(body: DishCreate, _s: dict = Depends(require_session)):
    return create_dish(body)


@router.put("/v1/kitchen/dishes/{dish_id}", response_model=Dish)
def api_update_dish(dish_id: str, body: DishCreate, _s: dict = Depends(require_session)):
    return update_dish(dish_id, body)


@router.delete("/v1/kitchen/dishes/{dish_id}")
def api_delete_dish(dish_id: str, _s: dict = Depends(require_session)):
    delete_dish(dish_id)
    return {"ok": True}


# --- canonical sources + evidence ---
@router.get("/v1/sources", response_model=list[CanonicalSource])
def api_list_sources(
    active_only: bool = Query(default=True),
    _s: dict = Depends(require_session),
):
    seed_official_fsa_placeholder()
    return list_sources(active_only=active_only)


@router.post("/v1/sources", response_model=CanonicalSource)
def api_create_source(body: CanonicalSourceCreate, _s: dict = Depends(require_session)):
    return create_source(body)


@router.get("/v1/cook/consultations/{cid}/evidence")
def api_consultation_evidence(cid: str, _s: dict = Depends(require_session)):
    if not get_consultation(cid):
        raise HTTPException(404, "consultation not found")
    bundle = get_consultation_evidence(cid) or {}
    evidence = [e.model_dump(mode="json") for e in list_evidence_for_consultation(cid)]
    return {"consultation_id": cid, "bundle": bundle, "evidence": evidence}


# --- consultations ---
@router.post("/v1/cook/consultations", response_model=CookConsultation)
def api_create_consultation(body: CookConsultationCreate, s: dict = Depends(require_session)):
    return create_consultation(body, actor=s.get("sub") or "session")


@router.get("/v1/cook/consultations", response_model=list[CookConsultation])
def api_list_consultations(
    active: bool = Query(default=False),
    _s: dict = Depends(require_session),
):
    reap_expired_leases()
    if active:
        return list_active_consultations()
    return list_consultations()


@router.get("/v1/cook/consultations/{cid}", response_model=CookConsultation)
def api_get_consultation(cid: str, _s: dict = Depends(require_session)):
    reap_expired_leases()
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "consultation not found")
    return c


@router.post("/v1/cook/consultations/{cid}/complete", response_model=CookConsultation)
def api_complete_consultation(cid: str, _s: dict = Depends(require_session)):
    from datetime import datetime, timezone

    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "consultation not found")
    now = datetime.now(timezone.utc)
    c = c.model_copy(
        update={
            "task_status": CookTaskStatus.needs_review,
            "updated_at": now,
            "audit": list(c.audit) + [{"at": now.isoformat(), "event": "user_complete"}],
        }
    )
    return save_consultation(c)


@router.post("/v1/cook/consultations/{cid}/save-dish", response_model=Dish)
def api_save_dish_from_consultation(
    cid: str,
    body: SaveDishFromConsultation,
    _s: dict = Depends(require_session),
):
    c = get_consultation(cid)
    if not c:
        raise HTTPException(404, "consultation not found")
    plan = c.local_safety_plan
    if isinstance(plan, dict):
        from .kitchen_models import CookStudioPlan

        plan = CookStudioPlan.model_validate(plan)
    if plan.rejected:
        raise HTTPException(409, "cannot save dish from blocked safety task")
    spine = plan.recipe_spine
    dish = create_dish(
        DishCreate(
            name=body.name or c.title,
            type=body.type,
            service_context=c.service_context,
            portions=c.covers_or_portions,
            recipe=spine if isinstance(spine, RecipeSpineFull) else RecipeSpineFull.model_validate(spine),
            allergens=c.allergens,
            status=body.status,
            source_refs=[{"consultation_id": c.id, "mode": c.mode.value}],
        )
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    c = c.model_copy(
        update={
            "dish_id": dish.id,
            "task_status": CookTaskStatus.saved_as_dish_or_component,
            "updated_at": now,
            "audit": list(c.audit)
            + [{"at": now.isoformat(), "event": "saved_as_dish", "dish_id": dish.id}],
        }
    )
    save_consultation(c)
    return dish


# --- Graph Recall worker (server-only token) ---
@router.get("/v1/graph-recall/jobs/lease", response_model=GraphRecallLeaseResponse)
def api_gr_lease(
    worker_id: str = Query(default="graph-recall"),
    timeout_s: float = Query(default=25.0, ge=0.5, le=60.0),
    _w: str = Depends(require_graph_recall),
):
    return long_poll_lease(worker_id=worker_id, timeout_s=timeout_s)


@router.post("/v1/graph-recall/jobs/result", response_model=CookConsultation)
def api_gr_result(body: GraphRecallResultRequest, _w: str = Depends(require_graph_recall)):
    return complete_result(body)
