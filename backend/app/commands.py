"""Server-side board commands + dispatch of host-facing work to the bridge queue."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .agents import capture_with_ai, capture_without_ai
from .config import get_settings
from . import jobs as job_queue
from .models import (
    HOST_FACING_COMMANDS,
    SERVER_SIDE_COMMANDS,
    ActionRecord,
    ActionStatus,
    Board,
    BridgeJob,
    CommandName,
    CommandRequest,
    CommandResponse,
    Freshness,
    ItemSource,
    Level,
    PlayState,
    TodayItem,
)
from .store import BoardStore, get_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _path_label(cassette: bool) -> str:
    return (
        "ytdl → mpv → ffmpeg cassette → out"
        if cassette
        else "ytdl → mpv → out"
    )


def _action_from_job(job: BridgeJob) -> ActionRecord:
    status_map = {
        "pending_approval": ActionStatus.pending_approval,
        "queued": ActionStatus.queued,
        "leased": ActionStatus.leased,
        "completed": ActionStatus.completed,
        "rejected": ActionStatus.rejected,
        "failed": ActionStatus.failed,
    }
    return ActionRecord(
        id=f"act-{job.id.removeprefix('job-')}",
        command=job.command,
        status=status_map.get(job.status.value, ActionStatus.accepted),
        source=job.source,
        actor=job.actor,
        payload=job.payload,
        result=job.result,
        message=job.message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        board_revision=job.board_revision,
        audit=job.audit,
        job_id=job.id,
    )


def execute_command(
    req: CommandRequest,
    *,
    store: BoardStore | None = None,
) -> CommandResponse:
    store = store or get_store()
    cmd = req.command

    route = req.route
    host_facing = cmd.value in HOST_FACING_COMMANDS
    if route == "auto":
        route = "bridge" if host_facing else "server"
    if route == "bridge" or host_facing:
        job = job_queue.enqueue(
            cmd,
            req.payload,
            actor=req.actor,
            source=req.source,
            require_approval=req.require_approval,
            client_id=req.client_id,
        )
        action = _action_from_job(job)
        store.save_action(action)
        return CommandResponse(action=action, board=store.get(), job=job)

    if cmd.value not in SERVER_SIDE_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"{cmd.value} must be routed to the debian bridge job queue",
        )

    now = _now()
    action = ActionRecord(
        command=cmd,
        status=ActionStatus.running,
        source=req.source,
        actor=req.actor,
        payload=req.payload,
        created_at=now,
        updated_at=now,
        audit={"route": "server"},
    )
    store.save_action(action)
    try:
        board, message, result = _run_server(store, req)
        action = action.model_copy(
            update={
                "status": ActionStatus.completed,
                "message": message,
                "result": result,
                "board_revision": board.meta.revision,
                "updated_at": _now(),
            }
        )
        store.save_action(action)
        return CommandResponse(action=action, board=board, job=None)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        action = action.model_copy(
            update={
                "status": ActionStatus.failed,
                "message": str(e),
                "updated_at": _now(),
            }
        )
        store.save_action(action)
        return CommandResponse(action=action, board=store.get(), job=None)


def approve_action(action_id: str, approve: bool, note: str = "", *, actor: str = "owner") -> CommandResponse:
    """Approve a *bridge job* — never executes host-facing work in-process."""
    store = get_store()
    # action_id may be act-… or job-…
    job_id = action_id
    if action_id.startswith("act-"):
        rec = store.get_action(action_id)
        if rec and rec.job_id:
            job_id = rec.job_id
        else:
            job_id = f"job-{action_id.removeprefix('act-')}"
    if not job_id.startswith("job-"):
        # try lookup by action
        rec = store.get_action(action_id)
        if rec and rec.job_id:
            job_id = rec.job_id
        else:
            raise HTTPException(status_code=404, detail="no bridge job for this action")

    job = job_queue.approve_job(job_id, approve, note, actor=actor)
    action = _action_from_job(job)
    store.save_action(action)
    return CommandResponse(action=action, board=store.get(), job=job)


def _run_server(store: BoardStore, req: CommandRequest) -> tuple[Board, str, dict[str, Any]]:
    cmd = req.command
    p = req.payload
    board = store.get()

    if cmd == CommandName.status:
        return board, board.meta.status.label, {"revision": board.meta.revision}

    if cmd == CommandName.capture:
        note = str(p.get("note") or p.get("text") or "").strip()
        if not note:
            raise HTTPException(status_code=422, detail="payload.note required")
        use_ai = bool(p.get("use_ai", True)) and get_settings().enable_pydantic_ai
        if use_ai:
            draft, used, provider = capture_with_ai(note)
        else:
            draft, used, provider = capture_without_ai(note), False, "none"
        item = TodayItem(
            text=f"{draft.title} — {draft.body}",
            kind="capture",
            tags=draft.tags,
            level=draft.level,
            source=ItemSource.capture,
            created_at=_now(),
            detail=draft.body,
        )
        items = list(board.today.items) + [item]
        board = store.set(
            board.model_copy(
                update={"today": board.today.model_copy(update={"items": items})}
            ),
            detail=f"capture:{draft.title}",
        )
        return board, draft.title, {
            "item_id": item.id,
            "used_ai": used,
            "ai_provider": provider,
        }

    if cmd == CommandName.add_today:
        text = str(p.get("text") or p.get("body") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="payload.text required")
        item = TodayItem(
            text=text,
            kind=p.get("kind") or "reminder",  # type: ignore[arg-type]
            tags=list(p.get("tags") or ["reminder"]),
            level=Level(p["level"]) if p.get("level") else Level.info,
            source=req.source,
            created_at=_now(),
        )
        items = list(board.today.items) + [item]
        board = store.set(
            board.model_copy(
                update={"today": board.today.model_copy(update={"items": items})}
            ),
            detail=f"add_today:{item.id}",
        )
        return board, f"added {item.id}", {"item_id": item.id}

    # Media mirror only — not a verified Debian mpv session
    media = board.media
    if cmd == CommandName.media_play:
        if not media.current and media.queue:
            head, *rest = media.queue
            media = media.model_copy(update={"current": head, "queue": rest})
        media = media.model_copy(
            update={
                "state": PlayState.playing,
                "note": "hosted media mirror (not verified mpv)",
            }
        )
        note = f"mirror play · {media.current.title if media.current else 'empty'}"
    elif cmd == CommandName.media_pause:
        media = media.model_copy(update={"state": PlayState.paused})
        note = "mirror pause"
    elif cmd == CommandName.media_stop:
        media = media.model_copy(update={"state": PlayState.idle})
        note = "mirror stop"
    elif cmd == CommandName.media_next:
        if not media.queue:
            return board, "queue empty", {}
        head, *rest = media.queue
        prev = media.current
        media = media.model_copy(
            update={
                "current": head,
                "queue": ([*rest, prev] if prev else rest),
                "state": PlayState.playing
                if media.state == PlayState.idle
                else media.state,
            }
        )
        note = f"mirror next · {head.title}"
    elif cmd == CommandName.media_cassette_on:
        media = media.model_copy(
            update={"cassette": True, "path_label": _path_label(True)}
        )
        note = "mirror cassette on"
    elif cmd == CommandName.media_cassette_off:
        media = media.model_copy(
            update={"cassette": False, "path_label": _path_label(False)}
        )
        note = "mirror cassette off"
    elif cmd == CommandName.media_volume:
        vol = int(p.get("volume", media.volume))
        vol = max(0, min(100, vol))
        media = media.model_copy(update={"volume": vol})
        note = f"mirror volume {vol}"
    else:
        raise HTTPException(status_code=400, detail=f"unhandled server command {cmd}")

    board = store.set(board.model_copy(update={"media": media}), detail=note)
    return board, note, media.model_dump(mode="json")
