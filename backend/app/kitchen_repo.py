"""CRUD for produce lots, ingredients, dishes, consultations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .db import dumps, get_conn, loads
from .kitchen_models import (
    CookConsultation,
    CookConsultationCreate,
    CookStudioPlan,
    CookTaskStatus,
    Dish,
    DishCreate,
    GraphRecallStatus,
    Ingredient,
    IngredientCreate,
    ProduceLot,
    ProduceLotCreate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# --- produce ---


def list_produce(*, status: str | None = None) -> list[ProduceLot]:
    c = get_conn()
    if status:
        rows = c.execute(
            "SELECT data_json FROM produce_lots WHERE status=? ORDER BY updated_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = c.execute("SELECT data_json FROM produce_lots ORDER BY updated_at DESC").fetchall()
    return [ProduceLot.model_validate(loads(r["data_json"])) for r in rows]


def get_produce(lot_id: str) -> ProduceLot | None:
    row = get_conn().execute("SELECT data_json FROM produce_lots WHERE id=?", (lot_id,)).fetchone()
    return ProduceLot.model_validate(loads(row["data_json"])) if row else None


def create_produce(body: ProduceLotCreate) -> ProduceLot:
    now = _now()
    lot = ProduceLot(
        **body.model_dump(),
        created_at=now,
        updated_at=now,
    )
    get_conn().execute(
        "INSERT INTO produce_lots(id, data_json, status, updated_at) VALUES (?,?,?,?)",
        (lot.id, dumps(lot.model_dump(mode="json")), lot.status.value, _iso(now)),
    )
    get_conn().commit()
    return lot


def update_produce(lot_id: str, body: ProduceLotCreate) -> ProduceLot:
    existing = get_produce(lot_id)
    if not existing:
        raise HTTPException(404, "produce lot not found")
    now = _now()
    lot = ProduceLot(
        id=lot_id,
        **body.model_dump(),
        created_at=existing.created_at or now,
        updated_at=now,
    )
    get_conn().execute(
        "UPDATE produce_lots SET data_json=?, status=?, updated_at=? WHERE id=?",
        (dumps(lot.model_dump(mode="json")), lot.status.value, _iso(now), lot_id),
    )
    get_conn().commit()
    return lot


def delete_produce(lot_id: str) -> None:
    cur = get_conn().execute("DELETE FROM produce_lots WHERE id=?", (lot_id,))
    get_conn().commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "produce lot not found")


# --- ingredients ---


def list_ingredients() -> list[Ingredient]:
    rows = get_conn().execute("SELECT data_json FROM ingredients ORDER BY name").fetchall()
    return [Ingredient.model_validate(loads(r["data_json"])) for r in rows]


def get_ingredient(ing_id: str) -> Ingredient | None:
    row = get_conn().execute("SELECT data_json FROM ingredients WHERE id=?", (ing_id,)).fetchone()
    return Ingredient.model_validate(loads(row["data_json"])) if row else None


def create_ingredient(body: IngredientCreate) -> Ingredient:
    now = _now()
    ing = Ingredient(**body.model_dump(), created_at=now, updated_at=now)
    get_conn().execute(
        "INSERT INTO ingredients(id, data_json, name, updated_at) VALUES (?,?,?,?)",
        (ing.id, dumps(ing.model_dump(mode="json")), ing.name, _iso(now)),
    )
    get_conn().commit()
    return ing


def update_ingredient(ing_id: str, body: IngredientCreate) -> Ingredient:
    existing = get_ingredient(ing_id)
    if not existing:
        raise HTTPException(404, "ingredient not found")
    now = _now()
    ing = Ingredient(
        id=ing_id,
        **body.model_dump(),
        created_at=existing.created_at or now,
        updated_at=now,
    )
    get_conn().execute(
        "UPDATE ingredients SET data_json=?, name=?, updated_at=? WHERE id=?",
        (dumps(ing.model_dump(mode="json")), ing.name, _iso(now), ing_id),
    )
    get_conn().commit()
    return ing


def delete_ingredient(ing_id: str) -> None:
    cur = get_conn().execute("DELETE FROM ingredients WHERE id=?", (ing_id,))
    get_conn().commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "ingredient not found")


# --- dishes ---


def list_dishes() -> list[Dish]:
    rows = get_conn().execute("SELECT data_json FROM dishes ORDER BY updated_at DESC").fetchall()
    return [Dish.model_validate(loads(r["data_json"])) for r in rows]


def get_dish(dish_id: str) -> Dish | None:
    row = get_conn().execute("SELECT data_json FROM dishes WHERE id=?", (dish_id,)).fetchone()
    return Dish.model_validate(loads(row["data_json"])) if row else None


def create_dish(body: DishCreate) -> Dish:
    now = _now()
    dish = Dish(
        **body.model_dump(),
        created_at=now,
        updated_at=now,
        audit=[{"at": _iso(now), "event": "created"}],
    )
    get_conn().execute(
        "INSERT INTO dishes(id, data_json, name, type, status, updated_at) VALUES (?,?,?,?,?,?)",
        (
            dish.id,
            dumps(dish.model_dump(mode="json")),
            dish.name,
            dish.type.value,
            dish.status.value,
            _iso(now),
        ),
    )
    get_conn().commit()
    return dish


def update_dish(dish_id: str, body: DishCreate) -> Dish:
    existing = get_dish(dish_id)
    if not existing:
        raise HTTPException(404, "dish not found")
    now = _now()
    audit = list(existing.audit) + [{"at": _iso(now), "event": "updated"}]
    dish = Dish(
        id=dish_id,
        **body.model_dump(),
        version=existing.version + 1,
        audit=audit,
        created_at=existing.created_at or now,
        updated_at=now,
    )
    get_conn().execute(
        "UPDATE dishes SET data_json=?, name=?, type=?, status=?, updated_at=? WHERE id=?",
        (
            dumps(dish.model_dump(mode="json")),
            dish.name,
            dish.type.value,
            dish.status.value,
            _iso(now),
            dish_id,
        ),
    )
    get_conn().commit()
    return dish


def delete_dish(dish_id: str) -> None:
    cur = get_conn().execute("DELETE FROM dishes WHERE id=?", (dish_id,))
    get_conn().commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "dish not found")


# --- consultations ---


def save_consultation(c: CookConsultation) -> CookConsultation:
    get_conn().execute(
        """
        INSERT INTO cook_consultations(id, data_json, mode, task_status, graph_recall_status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          data_json=excluded.data_json,
          mode=excluded.mode,
          task_status=excluded.task_status,
          graph_recall_status=excluded.graph_recall_status,
          updated_at=excluded.updated_at
        """,
        (
            c.id,
            dumps(c.model_dump(mode="json")),
            c.mode.value,
            c.task_status.value,
            c.graph_recall_status.value,
            _iso(c.created_at),
            _iso(c.updated_at),
        ),
    )
    get_conn().commit()
    try:
        from .store import get_store

        get_store().emit_cook_task(c)
    except Exception:  # noqa: BLE001
        pass
    return c


def get_consultation(cid: str) -> CookConsultation | None:
    row = get_conn().execute("SELECT data_json FROM cook_consultations WHERE id=?", (cid,)).fetchone()
    return CookConsultation.model_validate(loads(row["data_json"])) if row else None


def list_consultations(limit: int = 40) -> list[CookConsultation]:
    rows = get_conn().execute(
        "SELECT data_json FROM cook_consultations ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [CookConsultation.model_validate(loads(r["data_json"])) for r in rows]


def list_active_consultations() -> list[CookConsultation]:
    active = {
        CookTaskStatus.draft.value,
        CookTaskStatus.safety_checked.value,
        CookTaskStatus.local_plan_ready.value,
        CookTaskStatus.kitchen_memory_queued.value,
        CookTaskStatus.kitchen_memory_working.value,
        CookTaskStatus.kitchen_memory_returned.value,
        CookTaskStatus.needs_review.value,
        CookTaskStatus.blocked.value,
    }
    all_c = list_consultations(80)
    return [c for c in all_c if c.task_status.value in active]


def new_consultation_id() -> str:
    return f"cook-{uuid4().hex[:12]}"
