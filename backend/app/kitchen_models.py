"""Cook Studio + kitchen library Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class StorageLocation(str, Enum):
    dry = "dry"
    fridge = "fridge"
    freezer = "freezer"
    pass_station = "pass"
    prep = "prep"


class TraceabilityStatus(str, Enum):
    labelled_chilled_known = "labelled_chilled_known"
    clean_raw_trim = "clean_raw_trim"
    unknown = "unknown"
    guest_exposed_buffet = "guest_exposed_buffet"


class ProduceStatus(str, Enum):
    available = "available"
    reserved = "reserved"
    used = "used"
    waste = "waste"
    quarantined = "quarantined"


class DishType(str, Enum):
    dish = "dish"
    component = "component"
    sauce = "sauce"
    garnish = "garnish"
    prep = "prep"


class DishStatus(str, Enum):
    draft = "draft"
    tested = "tested"
    approved = "approved"
    retired = "retired"


class CookMode(str, Enum):
    build = "build"
    rescue = "rescue"
    service = "service"
    develop = "develop"


class GraphRecallStatus(str, Enum):
    not_requested = "not_requested"
    queued = "queued"
    leased = "leased"
    completed = "completed"
    failed = "failed"


class CookTaskStatus(str, Enum):
    draft = "draft"
    safety_checked = "safety_checked"
    local_plan_ready = "local_plan_ready"
    kitchen_memory_queued = "kitchen_memory_queued"
    kitchen_memory_working = "kitchen_memory_working"
    kitchen_memory_returned = "kitchen_memory_returned"
    needs_review = "needs_review"
    saved_as_dish_or_component = "saved_as_dish_or_component"
    blocked = "blocked"
    failed = "failed"


class ServiceContext(str, Enum):
    canteen = "canteen"
    staff_meal = "staff_meal"
    breakfast = "breakfast"
    banqueting = "banqueting"
    a_la_carte = "a_la_carte"
    home = "home"
    undecided = "undecided"
    pass_station = "pass"


class ProduceLot(BaseModel):
    id: str = Field(default_factory=lambda: f"lot-{uuid4().hex[:10]}")
    name: str
    supplier_source: str = ""
    quantity: float = 0
    unit: str = "kg"
    received_at: datetime | None = None
    opened_at: datetime | None = None
    use_by: datetime | None = None
    storage_location: StorageLocation = StorageLocation.fridge
    traceability: TraceabilityStatus = TraceabilityStatus.labelled_chilled_known
    holding_temp_c: float | None = None
    allergens: list[str] = Field(default_factory=list)
    status: ProduceStatus = ProduceStatus.available
    ingredient_id: str | None = None
    notes: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProduceLotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    supplier_source: str = ""
    quantity: float = 0
    unit: str = "kg"
    received_at: datetime | None = None
    opened_at: datetime | None = None
    use_by: datetime | None = None
    storage_location: StorageLocation = StorageLocation.fridge
    traceability: TraceabilityStatus = TraceabilityStatus.labelled_chilled_known
    holding_temp_c: float | None = None
    allergens: list[str] = Field(default_factory=list)
    status: ProduceStatus = ProduceStatus.available
    ingredient_id: str | None = None
    notes: str = ""


class Ingredient(BaseModel):
    id: str = Field(default_factory=lambda: f"ing-{uuid4().hex[:10]}")
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str = ""
    allergens: list[str] = Field(default_factory=list)
    storage_guidance: str = ""
    shelf_life_notes: str = ""
    yield_notes: str = ""
    seasonality: str = ""
    techniques: list[str] = Field(default_factory=list)
    flavour_notes: str = ""
    graph_sources: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IngredientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    category: str = ""
    allergens: list[str] = Field(default_factory=list)
    storage_guidance: str = ""
    shelf_life_notes: str = ""
    yield_notes: str = ""
    seasonality: str = ""
    techniques: list[str] = Field(default_factory=list)
    flavour_notes: str = ""
    graph_sources: list[dict[str, str]] = Field(default_factory=list)


class RecipeSpineFull(BaseModel):
    purpose: str = ""
    mise: str = ""
    method: str = ""
    holding_regeneration: str = ""
    pass_finish: str = ""
    failure_recovery: str = ""


class DishLink(BaseModel):
    ingredient_id: str | None = None
    component_dish_id: str | None = None
    name: str = ""
    quantity: float | None = None
    unit: str = ""


class Dish(BaseModel):
    id: str = Field(default_factory=lambda: f"dish-{uuid4().hex[:10]}")
    name: str
    type: DishType = DishType.dish
    service_context: ServiceContext = ServiceContext.undecided
    portions: int | None = None
    cost_target: str = ""
    recipe: RecipeSpineFull = Field(default_factory=RecipeSpineFull)
    allergens: list[str] = Field(default_factory=list)
    links: list[DishLink] = Field(default_factory=list)
    status: DishStatus = DishStatus.draft
    source_refs: list[dict[str, str]] = Field(default_factory=list)
    version: int = 1
    audit: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DishCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: DishType = DishType.dish
    service_context: ServiceContext = ServiceContext.undecided
    portions: int | None = None
    cost_target: str = ""
    recipe: RecipeSpineFull = Field(default_factory=RecipeSpineFull)
    allergens: list[str] = Field(default_factory=list)
    links: list[DishLink] = Field(default_factory=list)
    status: DishStatus = DishStatus.draft
    source_refs: list[dict[str, str]] = Field(default_factory=list)


class KitchenMemoryItem(BaseModel):
    title: str
    path: str = ""
    relevance: str = ""
    excerpt: str = ""


class CookStudioPlan(BaseModel):
    decision: dict[str, Any]
    recommended_action: str = ""
    primary_plan: dict[str, Any] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    recipe_spine: RecipeSpineFull = Field(default_factory=RecipeSpineFull)
    allergen_checks: list[str] = Field(default_factory=list)
    service_checks: list[str] = Field(default_factory=list)
    disposal_checklist: list[str] = Field(default_factory=list)
    kitchen_memory: list[KitchenMemoryItem] = Field(default_factory=list)
    guest_service_allowed: bool = False
    rejected: bool = False
    notes: list[str] = Field(default_factory=list)


class CookConsultationCreate(BaseModel):
    mode: CookMode
    title: str = ""
    ingredients_or_problem: str = Field(default="", max_length=4000)
    produce_lot_ids: list[str] = Field(default_factory=list)
    ingredient_ids: list[str] = Field(default_factory=list)
    dish_id: str | None = None
    traceability: TraceabilityStatus = TraceabilityStatus.labelled_chilled_known
    service_context: ServiceContext = ServiceContext.undecided
    allergens: list[str] = Field(default_factory=list)
    covers_or_portions: int | None = None
    time_available_minutes: int | None = None
    equipment: list[str] = Field(default_factory=list)
    desired_outcome: str = ""
    request_graph_recall: bool = True


class CookConsultation(BaseModel):
    id: str
    mode: CookMode
    title: str
    ingredients_or_problem: str
    produce_lot_ids: list[str] = Field(default_factory=list)
    ingredient_ids: list[str] = Field(default_factory=list)
    dish_id: str | None = None
    traceability: TraceabilityStatus
    service_context: ServiceContext
    allergens: list[str] = Field(default_factory=list)
    covers_or_portions: int | None = None
    time_available_minutes: int | None = None
    equipment: list[str] = Field(default_factory=list)
    desired_outcome: str = ""
    local_safety_plan: CookStudioPlan | dict[str, Any] = Field(default_factory=dict)
    graph_recall_status: GraphRecallStatus = GraphRecallStatus.not_requested
    graph_recall_response: dict[str, Any] | None = None
    task_status: CookTaskStatus = CookTaskStatus.draft
    audit: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    blocked_reason: str | None = None


class GraphRecallLeaseResponse(BaseModel):
    job: dict[str, Any] | None = None
    wait_ms: int = 0


class GraphRecallResultRequest(BaseModel):
    consultation_id: str
    status: Literal["completed", "failed"]
    kitchen_memory: list[dict[str, Any]] = Field(default_factory=list)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    worker_id: str = "graph-recall"
    lease_nonce: str = ""
    signature: str = ""
    # worker may suggest routes but cannot override safety
    proposed_guest_service: bool | None = None


class SaveDishFromConsultation(BaseModel):
    name: str | None = None
    type: DishType = DishType.dish
    status: DishStatus = DishStatus.draft
