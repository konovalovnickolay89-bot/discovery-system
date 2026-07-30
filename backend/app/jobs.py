"""Durable SQLite bridge job queue with lease nonces and canonical HMAC results."""

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
from .db import connect, dumps, loads
from .models import (
    BRIDGE_ALLOWLIST,
    HOST_FACING_COMMANDS,
    SYSTEM_CHANGING,
    BridgeJob,
    BridgeJobLeaseResponse,
    BridgeJobResultRequest,
    BridgeJobStatus,
    CommandName,
    ItemSource,
)

log = logging.getLogger("casual_board.jobs")
_wake = threading.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def bridge_secret() -> str:
    s = get_settings()
    tok = s.bridge_token.strip()
    if not tok:
        # open-dev fallback only
        return s.api_token.strip() or "open-dev-bridge"
    return tok


def canonical_result_payload(
    *,
    job_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    result: dict[str, Any],
    message: str,
    board_patch: dict[str, Any] | None,
) -> str:
    """Single canonical string used for HMAC (stable key order)."""
    obj = {
        "board_patch": board_patch if board_patch is not None else None,
        "job_id": job_id,
        "lease_nonce": lease_nonce,
        "message": message or "",
        "result": result or {},
        "status": status,
        "worker_id": worker_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sign_result(
    *,
    job_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    result: dict[str, Any],
    message: str = "",
    board_patch: dict[str, Any] | None = None,
) -> str:
    raw = canonical_result_payload(
        job_id=job_id,
        status=status,
        worker_id=worker_id,
        lease_nonce=lease_nonce,
        result=result,
        message=message,
        board_patch=board_patch,
    )
    return hmac.new(bridge_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()


def verify_result_signature(body: BridgeJobResultRequest) -> bool:
    expected = sign_result(
        job_id=body.job_id,
        status=body.status,
        worker_id=body.worker_id,
        lease_nonce=body.lease_nonce,
        result=body.result,
        message=body.message,
        board_patch=body.board_patch,
    )
    return hmac.compare_digest(expected, (body.signature or "").strip())


def _row_to_job(row: Any) -> BridgeJob:
    return BridgeJob(
        id=row["id"],
        command=CommandName(row["command"]),
        status=BridgeJobStatus(row["status"]),
        payload=loads(row["payload_json"], {}),
        actor=row["actor"] or "",
        source=ItemSource(row["source"] or "web"),
        client_id=row["client_id"],
        created_at=_parse_dt(row["created_at"]) or _now(),
        updated_at=_parse_dt(row["updated_at"]) or _now(),
        message=row["message"] or "",
        result=loads(row["result_json"], None),
        leased_by=row["leased_by"],
        lease_nonce=row["lease_nonce"],
        lease_expires_at=_parse_dt(row["lease_expires_at"]),
        board_revision=row["board_revision"],
        audit=loads(row["audit_json"], {}),
    )


def _conn():
    return connect(get_settings().sqlite_path)


def _save(job: BridgeJob) -> BridgeJob:
    c = _conn()
    c.execute(
        """
        INSERT INTO bridge_jobs (
            id, command, status, payload_json, actor, source, client_id,
            message, result_json, leased_by, lease_nonce, lease_expires_at,
            board_revision, audit_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            message=excluded.message,
            result_json=excluded.result_json,
            leased_by=excluded.leased_by,
            lease_nonce=excluded.lease_nonce,
            lease_expires_at=excluded.lease_expires_at,
            board_revision=excluded.board_revision,
            audit_json=excluded.audit_json,
            updated_at=excluded.updated_at
        """,
        (
            job.id,
            job.command.value,
            job.status.value,
            dumps(job.payload),
            job.actor,
            job.source.value,
            job.client_id,
            job.message,
            dumps(job.result) if job.result is not None else None,
            job.leased_by,
            job.lease_nonce,
            _iso(job.lease_expires_at),
            job.board_revision,
            dumps(job.audit),
            _iso(job.created_at),
            _iso(job.updated_at),
        ),
    )
    c.commit()
    try:
        from .store import get_store

        get_store().emit_job(job)
    except Exception:  # noqa: BLE001
        pass
    _wake.set()
    return job


def get_job(job_id: str) -> BridgeJob | None:
    row = _conn().execute("SELECT * FROM bridge_jobs WHERE id=?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def enqueue(
    command: CommandName,
    payload: dict[str, Any],
    *,
    actor: str,
    source: ItemSource,
    require_approval: bool | None = None,
    client_id: str | None = None,
) -> BridgeJob:
    if command.value not in BRIDGE_ALLOWLIST:
        raise HTTPException(status_code=403, detail=f"{command.value} not bridge-allowlisted")
    if command.value not in HOST_FACING_COMMANDS and source != ItemSource.bridge:
        raise HTTPException(status_code=400, detail=f"{command.value} is not host-facing")

    needs = (
        require_approval
        if require_approval is not None
        else (command.value in SYSTEM_CHANGING)
    )
    now = _now()
    job = BridgeJob(
        id=f"job-{uuid4().hex[:12]}",
        command=command,
        status=BridgeJobStatus.pending_approval if needs else BridgeJobStatus.queued,
        payload=payload,
        actor=actor,
        source=source,
        client_id=client_id,
        created_at=now,
        updated_at=now,
        message="awaiting approval" if needs else "queued for debian bridge",
        audit={"queued_by": actor, "host_facing": True},
    )
    return _save(job)


def approve_job(job_id: str, approve: bool, note: str = "", *, actor: str = "owner") -> BridgeJob:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != BridgeJobStatus.pending_approval:
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
    now = _now()
    if not approve:
        job = job.model_copy(
            update={
                "status": BridgeJobStatus.rejected,
                "message": note or "rejected",
                "updated_at": now,
                "audit": {**job.audit, "rejected_by": actor},
            }
        )
    else:
        job = job.model_copy(
            update={
                "status": BridgeJobStatus.queued,
                "message": note or "approved — queued for debian bridge",
                "updated_at": now,
                "audit": {**job.audit, "approved_by": actor},
            }
        )
    return _save(job)


def _expire_leases() -> None:
    now = _now()
    c = _conn()
    rows = c.execute(
        "SELECT * FROM bridge_jobs WHERE status='leased' AND lease_expires_at IS NOT NULL"
    ).fetchall()
    for row in rows:
        exp = _parse_dt(row["lease_expires_at"])
        if exp and exp < now:
            job = _row_to_job(row)
            job = job.model_copy(
                update={
                    "status": BridgeJobStatus.queued,
                    "leased_by": None,
                    "lease_nonce": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "message": "lease expired — requeued",
                }
            )
            _save(job)


def long_poll_lease(
    *,
    worker_id: str,
    timeout_s: float = 25.0,
    lease_s: float | None = None,
) -> BridgeJobLeaseResponse:
    lease_s = lease_s or float(get_settings().lease_ttl_s)
    deadline = time.monotonic() + max(0.5, timeout_s)
    while True:
        _expire_leases()
        c = _conn()
        row = c.execute(
            "SELECT * FROM bridge_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row:
            job = _row_to_job(row)
            nonce = secrets.token_hex(16)
            now = _now()
            exp = datetime.fromtimestamp(time.time() + lease_s, tz=timezone.utc)
            leased = job.model_copy(
                update={
                    "status": BridgeJobStatus.leased,
                    "leased_by": worker_id,
                    "lease_nonce": nonce,
                    "lease_expires_at": exp,
                    "updated_at": now,
                    "message": f"leased by {worker_id}",
                    "audit": {**job.audit, "leased_by": worker_id, "lease_nonce": nonce},
                }
            )
            # optimistic lock: only if still queued
            cur = c.execute(
                """
                UPDATE bridge_jobs SET status='leased', leased_by=?, lease_nonce=?,
                lease_expires_at=?, message=?, updated_at=?, audit_json=?
                WHERE id=? AND status='queued'
                """,
                (
                    worker_id,
                    nonce,
                    _iso(exp),
                    leased.message,
                    _iso(now),
                    dumps(leased.audit),
                    job.id,
                ),
            )
            c.commit()
            if cur.rowcount == 1:
                try:
                    from .store import get_store

                    get_store().emit_job(leased)
                except Exception:  # noqa: BLE001
                    pass
                return BridgeJobLeaseResponse(job=leased, wait_ms=0)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return BridgeJobLeaseResponse(job=None, wait_ms=int(timeout_s * 1000))
        _wake.clear()
        _wake.wait(timeout=min(1.0, remaining))


def complete_job(body: BridgeJobResultRequest) -> BridgeJob:
    if body.status not in {BridgeJobStatus.completed.value, BridgeJobStatus.failed.value}:
        raise HTTPException(status_code=422, detail="status must be completed|failed")
    if not body.lease_nonce.strip():
        raise HTTPException(status_code=422, detail="lease_nonce required")
    if not body.worker_id.strip():
        raise HTTPException(status_code=422, detail="worker_id required")
    if not verify_result_signature(body):
        raise HTTPException(status_code=401, detail="invalid bridge result signature")

    # replay protection
    c = _conn()
    if c.execute("SELECT 1 FROM used_nonces WHERE nonce=?", (body.lease_nonce,)).fetchone():
        raise HTTPException(status_code=409, detail="lease nonce already used (replay)")

    job = get_job(body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != BridgeJobStatus.leased:
        raise HTTPException(status_code=409, detail=f"job is not leased (status={job.status.value})")
    if job.leased_by != body.worker_id:
        raise HTTPException(status_code=403, detail="worker_id does not own lease")
    if not job.lease_nonce or not hmac.compare_digest(job.lease_nonce, body.lease_nonce):
        raise HTTPException(status_code=403, detail="lease_nonce mismatch")
    if job.lease_expires_at and job.lease_expires_at < _now():
        raise HTTPException(status_code=409, detail="lease expired")

    now = _now()
    st = BridgeJobStatus(body.status)
    job = job.model_copy(
        update={
            "status": st,
            "result": body.result,
            "message": body.message or st.value,
            "updated_at": now,
            "leased_by": None,
            "lease_nonce": None,
            "lease_expires_at": None,
            "audit": {
                **job.audit,
                "bridge_worker": body.worker_id,
                "signed": True,
                "executor": body.executor_note,
                "completed_nonce": body.lease_nonce,
            },
        }
    )
    c.execute(
        "INSERT INTO used_nonces(nonce, job_id, used_at) VALUES (?,?,?)",
        (body.lease_nonce, body.job_id, _iso(now)),
    )
    c.commit()
    job = _save(job)

    if st == BridgeJobStatus.completed and body.board_patch:
        _apply_board_patch(body.board_patch, actor=body.worker_id or "bridge")
        from .store import get_store

        job = job.model_copy(update={"board_revision": get_store().get().meta.revision})
        _save(job)
    return job


def _apply_board_patch(patch: dict[str, Any], *, actor: str) -> None:
    from .models import MachineSection, MediaSection
    from .store import get_store

    store = get_store()
    board = store.get()
    updates: dict[str, Any] = {}
    if "machine" in patch and isinstance(patch["machine"], dict):
        m = board.machine.model_dump()
        m.update({k: v for k, v in patch["machine"].items() if k in MachineSection.model_fields})
        updates["machine"] = MachineSection.model_validate(m).with_health()
    if "media" in patch and isinstance(patch["media"], dict):
        m = board.media.model_dump()
        m.update({k: v for k, v in patch["media"].items() if k in MediaSection.model_fields})
        updates["media"] = MediaSection.model_validate(m)
    if "remove_today_id" in patch:
        tid = str(patch["remove_today_id"])
        items = [i for i in board.today.items if i.id != tid]
        updates["today"] = board.today.model_copy(update={"items": items})
    if updates:
        store.set(board.model_copy(update=updates), detail=f"bridge_patch:{actor}")


def reset_jobs_for_tests() -> None:
    """Wipe jobs table (tests only)."""
    from .db import close

    close()
    path = get_settings().sqlite_path
    if path.exists():
        path.unlink()
    connect(path)
