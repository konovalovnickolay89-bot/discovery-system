"""Separate culinary Graph Recall consultation queue (not host-command bridge)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .config import get_settings
from .db import dumps, get_conn, loads
from .kitchen_models import (
    CookConsultation,
    CookTaskStatus,
    GraphRecallLeaseResponse,
    GraphRecallResultRequest,
    GraphRecallStatus,
)
from .kitchen_repo import get_consultation, get_dish, get_ingredient, get_produce, save_consultation

log = logging.getLogger("casual_board.graph_recall")
_wake = threading.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def graph_recall_secret() -> str:
    s = get_settings()
    tok = (s.graph_recall_token or "").strip()
    if not tok:
        return s.bridge_token.strip() or s.api_token.strip() or "open-dev-graph-recall"
    return tok


def canonical_result_payload(
    *,
    consultation_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    kitchen_memory: list,
    enrichment: dict,
    message: str,
) -> str:
    obj = {
        "consultation_id": consultation_id,
        "enrichment": enrichment or {},
        "kitchen_memory": kitchen_memory or [],
        "lease_nonce": lease_nonce,
        "message": message or "",
        "status": status,
        "worker_id": worker_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sign_result(**kwargs: Any) -> str:
    raw = canonical_result_payload(**kwargs)
    return hmac.new(graph_recall_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()


def verify_result(body: GraphRecallResultRequest) -> bool:
    expected = sign_result(
        consultation_id=body.consultation_id,
        status=body.status,
        worker_id=body.worker_id,
        lease_nonce=body.lease_nonce,
        kitchen_memory=body.kitchen_memory,
        enrichment=body.enrichment,
        message=body.message,
    )
    return hmac.compare_digest(expected, (body.signature or "").strip())


def enqueue_graph_recall(c: CookConsultation) -> str:
    """Queue a Graph Recall job for a consultation (server-side only)."""
    job_id = f"gr-{uuid4().hex[:12]}"
    now = _now()
    # payload for worker: validated state + linked records
    lots = [get_produce(i).model_dump(mode="json") for i in c.produce_lot_ids if get_produce(i)]
    ings = [get_ingredient(i).model_dump(mode="json") for i in c.ingredient_ids if get_ingredient(i)]
    dish = get_dish(c.dish_id).model_dump(mode="json") if c.dish_id and get_dish(c.dish_id) else None
    payload = {
        "consultation": c.model_dump(mode="json"),
        "produce_lots": lots,
        "ingredients": ings,
        "dish": dish,
        "mode_contract": {
            "build": "strategic_application",
            "service": "strategic_application",
            "rescue": "strategic_application_strict_safety",
            "develop": "creative_layer_max_3",
        }.get(c.mode.value, "strategic_application"),
        "rules": [
            "Never override local safety",
            "Database Expansion is never automatic",
            "Return kitchen_memory with title/path/relevance",
        ],
    }
    get_conn().execute(
        """
        INSERT INTO graph_recall_jobs(
          id, consultation_id, status, payload_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (job_id, c.id, "queued", dumps(payload), _iso(now), _iso(now)),
    )
    get_conn().commit()
    _wake.set()
    return job_id


def long_poll_lease(*, worker_id: str, timeout_s: float = 25.0) -> GraphRecallLeaseResponse:
    lease_s = float(get_settings().lease_ttl_s)
    deadline = time.monotonic() + max(0.5, timeout_s)
    while True:
        _expire()
        row = get_conn().execute(
            "SELECT * FROM graph_recall_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row:
            nonce = secrets.token_hex(16)
            now = _now()
            exp = datetime.fromtimestamp(time.time() + lease_s, tz=timezone.utc)
            cur = get_conn().execute(
                """
                UPDATE graph_recall_jobs SET status='leased', leased_by=?, lease_nonce=?,
                lease_expires_at=?, updated_at=? WHERE id=? AND status='queued'
                """,
                (worker_id, nonce, _iso(exp), _iso(now), row["id"]),
            )
            get_conn().commit()
            if cur.rowcount == 1:
                # mark consultation working
                c = get_consultation(row["consultation_id"])
                if c:
                    c = c.model_copy(
                        update={
                            "graph_recall_status": GraphRecallStatus.leased,
                            "task_status": CookTaskStatus.kitchen_memory_working,
                            "updated_at": now,
                            "audit": list(c.audit)
                            + [{"at": now.isoformat(), "event": "kitchen_memory_working", "worker": worker_id}],
                        }
                    )
                    save_consultation(c)
                job = {
                    "id": row["id"],
                    "consultation_id": row["consultation_id"],
                    "status": "leased",
                    "lease_nonce": nonce,
                    "leased_by": worker_id,
                    "lease_expires_at": _iso(exp),
                    "payload": loads(row["payload_json"]),
                }
                return GraphRecallLeaseResponse(job=job, wait_ms=0)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return GraphRecallLeaseResponse(job=None, wait_ms=int(timeout_s * 1000))
        _wake.clear()
        _wake.wait(timeout=min(1.0, remaining))


def _expire() -> None:
    now = _now()
    rows = get_conn().execute(
        "SELECT * FROM graph_recall_jobs WHERE status='leased' AND lease_expires_at IS NOT NULL"
    ).fetchall()
    for row in rows:
        exp = _parse(row["lease_expires_at"])
        if exp and exp < now:
            get_conn().execute(
                """
                UPDATE graph_recall_jobs SET status='queued', leased_by=NULL, lease_nonce=NULL,
                lease_expires_at=NULL, message='lease expired', updated_at=? WHERE id=?
                """,
                (_iso(now), row["id"]),
            )
            get_conn().commit()


def complete_result(body: GraphRecallResultRequest) -> CookConsultation:
    if body.status not in {"completed", "failed"}:
        raise HTTPException(422, "status must be completed|failed")
    if not body.lease_nonce.strip() or not body.worker_id.strip():
        raise HTTPException(422, "worker_id and lease_nonce required")
    if not verify_result(body):
        raise HTTPException(401, "invalid graph recall signature")

    c = get_conn()
    if c.execute("SELECT 1 FROM graph_recall_nonces WHERE nonce=?", (body.lease_nonce,)).fetchone():
        raise HTTPException(409, "lease nonce already used (replay)")

    row = c.execute(
        "SELECT * FROM graph_recall_jobs WHERE consultation_id=? AND status='leased' ORDER BY updated_at DESC LIMIT 1",
        (body.consultation_id,),
    ).fetchone()
    if not row:
        raise HTTPException(409, "no active lease for consultation")
    if row["leased_by"] != body.worker_id:
        raise HTTPException(403, "worker_id does not own lease")
    if not row["lease_nonce"] or not hmac.compare_digest(row["lease_nonce"], body.lease_nonce):
        raise HTTPException(403, "lease_nonce mismatch")
    exp = _parse(row["lease_expires_at"])
    if exp and exp < _now():
        raise HTTPException(409, "lease expired")

    now = _now()
    c.execute(
        "INSERT INTO graph_recall_nonces(nonce, job_id, used_at) VALUES (?,?,?)",
        (body.lease_nonce, row["id"], _iso(now)),
    )
    c.execute(
        """
        UPDATE graph_recall_jobs SET status=?, result_json=?, message=?, leased_by=NULL,
        lease_nonce=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?
        """,
        (
            body.status,
            dumps({"kitchen_memory": body.kitchen_memory, "enrichment": body.enrichment}),
            body.message,
            _iso(now),
            row["id"],
        ),
    )
    c.commit()

    consultation = get_consultation(body.consultation_id)
    if not consultation:
        raise HTTPException(404, "consultation not found")

    if body.status == "failed":
        consultation = consultation.model_copy(
            update={
                "graph_recall_status": GraphRecallStatus.failed,
                "task_status": CookTaskStatus.needs_review
                if not (
                    isinstance(consultation.local_safety_plan, dict)
                    and consultation.local_safety_plan.get("rejected")
                )
                else CookTaskStatus.blocked,
                "updated_at": now,
                "blocked_reason": body.message or "Kitchen memory failed",
                "audit": list(consultation.audit)
                + [{"at": now.isoformat(), "event": "kitchen_memory_failed", "message": body.message}],
            }
        )
        return save_consultation(consultation)

    from .cook_studio import merge_kitchen_memory

    return merge_kitchen_memory(
        consultation,
        body.kitchen_memory,
        body.enrichment,
        proposed_guest_service=body.proposed_guest_service,
    )
