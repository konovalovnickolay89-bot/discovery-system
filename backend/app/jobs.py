"""Debian bridge job queue.

Hosted API only *queues* host-facing work. Approval moves a job to ``queued``.
The Debian bridge long-polls outbound, leases work, hands it to a local executor
hook (Hermes/Linux-Wiki), then POSTs a signed result. FastAPI never executes
host-facing actions on approval.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .config import get_settings
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
from .store import get_store

log = logging.getLogger("casual_board.jobs")

_lock = threading.RLock()
_jobs: dict[str, BridgeJob] = {}
_waiters: list[threading.Event] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def bridge_secret() -> str:
    s = get_settings()
    return (s.bridge_token or s.api_token or "").strip()


def sign_payload(job_id: str, status: str, body: dict[str, Any]) -> str:
    secret = bridge_secret()
    if not secret:
        return "open-dev"
    raw = f"{job_id}|{status}|{json.dumps(body, sort_keys=True, default=str)}"
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(job_id: str, status: str, body: dict[str, Any], signature: str) -> bool:
    secret = bridge_secret()
    if not secret:
        return True  # open-dev
    expected = sign_payload(job_id, status, body)
    return hmac.compare_digest(expected, (signature or "").strip())


def _wake() -> None:
    for ev in list(_waiters):
        ev.set()


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
        # only host-facing (or explicit bridge source) enter this queue
        raise HTTPException(status_code=400, detail=f"{command.value} is not a host-facing bridge job")

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
    with _lock:
        _jobs[job.id] = job
        get_store().append_job_log(job)
    _wake()
    log.info("job enqueued id=%s cmd=%s status=%s", job.id, job.command, job.status)
    return job


def get_job(job_id: str) -> BridgeJob | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(status: BridgeJobStatus | None = None, limit: int = 50) -> list[BridgeJob]:
    with _lock:
        items = list(_jobs.values())
    if status:
        items = [j for j in items if j.status == status]
    items.sort(key=lambda j: j.created_at)
    return items[:limit]


def approve_job(job_id: str, approve: bool, note: str = "", *, actor: str = "owner") -> BridgeJob:
    """Approval only transitions pending_approval → queued|rejected. Never runs host work."""
    with _lock:
        job = _jobs.get(job_id)
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
                    "audit": {**job.audit, "rejected_by": actor, "note": note},
                }
            )
        else:
            job = job.model_copy(
                update={
                    "status": BridgeJobStatus.queued,
                    "message": note or "approved — queued for debian bridge",
                    "updated_at": now,
                    "audit": {**job.audit, "approved_by": actor, "note": note},
                }
            )
        _jobs[job_id] = job
        get_store().append_job_log(job)
    if approve:
        _wake()
    log.info("job approval id=%s approve=%s → %s", job_id, approve, job.status)
    return job


def long_poll_lease(
    *,
    worker_id: str,
    timeout_s: float = 25.0,
    lease_s: float = 60.0,
) -> BridgeJobLeaseResponse:
    """Block until a queued job is available or timeout. Outbound-only bridge calls this."""
    deadline = time.monotonic() + max(0.5, timeout_s)
    while True:
        with _lock:
            for job in sorted(_jobs.values(), key=lambda j: j.created_at):
                if job.status == BridgeJobStatus.queued:
                    now = _now()
                    leased = job.model_copy(
                        update={
                            "status": BridgeJobStatus.leased,
                            "leased_by": worker_id,
                            "lease_expires_at": datetime.fromtimestamp(
                                time.time() + lease_s, tz=timezone.utc
                            ),
                            "updated_at": now,
                            "message": f"leased by {worker_id}",
                            "audit": {**job.audit, "leased_by": worker_id},
                        }
                    )
                    _jobs[job.id] = leased
                    get_store().append_job_log(leased)
                    return BridgeJobLeaseResponse(job=leased, wait_ms=0)
            # expire stale leases → requeue
            now_ts = time.time()
            for jid, job in list(_jobs.items()):
                if (
                    job.status == BridgeJobStatus.leased
                    and job.lease_expires_at
                    and job.lease_expires_at.timestamp() < now_ts
                ):
                    req = job.model_copy(
                        update={
                            "status": BridgeJobStatus.queued,
                            "leased_by": None,
                            "lease_expires_at": None,
                            "updated_at": _now(),
                            "message": "lease expired — requeued",
                        }
                    )
                    _jobs[jid] = req
                    get_store().append_job_log(req)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return BridgeJobLeaseResponse(job=None, wait_ms=int(timeout_s * 1000))
        ev = threading.Event()
        with _lock:
            _waiters.append(ev)
        ev.wait(timeout=min(1.0, remaining))
        with _lock:
            if ev in _waiters:
                _waiters.remove(ev)


def complete_job(body: BridgeJobResultRequest) -> BridgeJob:
    """Accept signed result from Debian bridge. Applies optional board_patch only from result."""
    if not verify_signature(body.job_id, body.status, body.result, body.signature):
        raise HTTPException(status_code=401, detail="invalid bridge result signature")
    if body.status not in {BridgeJobStatus.completed.value, BridgeJobStatus.failed.value}:
        raise HTTPException(status_code=422, detail="result status must be completed|failed")

    with _lock:
        job = _jobs.get(body.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status not in {BridgeJobStatus.leased, BridgeJobStatus.queued}:
            raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
        now = _now()
        st = BridgeJobStatus(body.status)
        job = job.model_copy(
            update={
                "status": st,
                "result": body.result,
                "message": body.message or st.value,
                "updated_at": now,
                "leased_by": None,
                "lease_expires_at": None,
                "audit": {
                    **job.audit,
                    "bridge_worker": body.worker_id,
                    "signed": True,
                    "executor": body.executor_note,
                },
            }
        )
        _jobs[body.job_id] = job
        get_store().append_job_log(job)

    # Optional board mirror update from bridge-reported facts (not host execution)
    if st == BridgeJobStatus.completed and body.board_patch:
        _apply_board_patch(body.board_patch, actor=body.worker_id or "bridge")

    board = get_store().get()
    job = job.model_copy(update={"board_revision": board.meta.revision})
    with _lock:
        _jobs[job.id] = job
    return job


def _apply_board_patch(patch: dict[str, Any], *, actor: str) -> None:
    """Apply limited section patches reported by the bridge after local execution."""
    from .models import MachineSection, MediaSection

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
    with _lock:
        _jobs.clear()
