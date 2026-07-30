"""Allowlisted command execution for web / CLI / bridge / Hermes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .agents import capture_with_ai, capture_without_ai
from .config import get_settings
from .models import (
    BRIDGE_ALLOWLIST,
    SYSTEM_CHANGING,
    ActionRecord,
    ActionStatus,
    Board,
    CommandName,
    CommandRequest,
    CommandResponse,
    Freshness,
    ItemSource,
    Level,
    MachineSection,
    MediaSection,
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


def execute_command(
    req: CommandRequest,
    *,
    store: BoardStore | None = None,
    from_bridge: bool = False,
) -> CommandResponse:
    store = store or get_store()
    now = _now()

    if from_bridge and req.command.value not in BRIDGE_ALLOWLIST:
        raise HTTPException(
            status_code=403,
            detail=f"command {req.command.value} not allowlisted for bridge",
        )

    needs_approval = req.require_approval or (
        from_bridge and req.command.value in SYSTEM_CHANGING
    )

    action = ActionRecord(
        command=req.command,
        status=ActionStatus.pending_approval if needs_approval else ActionStatus.running,
        source=req.source,
        actor=req.actor,
        payload=req.payload,
        created_at=now,
        updated_at=now,
        audit={
            "from_bridge": from_bridge,
            "client_id": req.client_id,
        },
    )
    store.save_action(action)

    if needs_approval:
        action = action.model_copy(
            update={
                "message": "awaiting explicit approval for system-changing action",
                "updated_at": _now(),
            }
        )
        store.save_action(action)
        return CommandResponse(action=action, board=store.get())

    try:
        board, message, result = _run(store, req)
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
        return CommandResponse(action=action, board=board)
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
        return CommandResponse(action=action, board=store.get())


def approve_action(action_id: str, approve: bool, note: str = "") -> CommandResponse:
    store = get_store()
    action = store.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="action not found")
    if action.status != ActionStatus.pending_approval:
        raise HTTPException(status_code=409, detail=f"action is {action.status}")

    if not approve:
        action = action.model_copy(
            update={
                "status": ActionStatus.rejected,
                "message": note or "rejected",
                "updated_at": _now(),
            }
        )
        store.save_action(action)
        return CommandResponse(action=action, board=store.get())

    req = CommandRequest(
        command=action.command,
        payload=action.payload,
        source=action.source,
        actor=action.actor,
        require_approval=False,
    )
    # mark previous as running then complete via _run
    action = action.model_copy(
        update={"status": ActionStatus.running, "updated_at": _now(), "message": note}
    )
    store.save_action(action)
    board, message, result = _run(store, req)
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
    return CommandResponse(action=action, board=board)


def _run(store: BoardStore, req: CommandRequest) -> tuple[Board, str, dict[str, Any]]:
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
        draft, used = (
            capture_with_ai(note) if use_ai else (capture_without_ai(note), False)
        )
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
        return board, draft.title, {"item_id": item.id, "used_ai": used}

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

    if cmd == CommandName.remove_today:
        tid = str(p.get("id") or "")
        if not tid:
            raise HTTPException(status_code=422, detail="payload.id required")
        items = [i for i in board.today.items if i.id != tid]
        board = store.set(
            board.model_copy(
                update={"today": board.today.model_copy(update={"items": items})}
            ),
            detail=f"remove_today:{tid}",
        )
        return board, f"removed {tid}", {"item_id": tid}

    if cmd == CommandName.set_media:
        m = board.media.model_dump()
        m.update({k: v for k, v in p.items() if k in MediaSection.model_fields})
        media = MediaSection.model_validate(m)
        media = media.model_copy(
            update={
                "path_label": _path_label(media.cassette),
                "freshness": Freshness.fresh,
            }
        )
        board = store.set(
            board.model_copy(update={"media": media}), detail="set_media"
        )
        return board, "media updated", media.model_dump(mode="json")

    if cmd == CommandName.set_machine:
        m = board.machine.model_dump()
        m.update({k: v for k, v in p.items() if k in MachineSection.model_fields})
        machine = MachineSection.model_validate(m).with_health()
        machine = machine.model_copy(
            update={"freshness": Freshness.fresh, "reported_at": _now()}
        )
        board = store.set(
            board.model_copy(update={"machine": machine}), detail="set_machine"
        )
        return board, "machine updated", machine.model_dump(mode="json")

    # Media transport mirrors (web UI / CLI) — Debian may also drive real mpv
    media = board.media
    if cmd == CommandName.media_play:
        if not media.current and media.queue:
            head, *rest = media.queue
            media = media.model_copy(update={"current": head, "queue": rest})
        media = media.model_copy(update={"state": PlayState.playing})
        note = f"mpv play · {media.current.title if media.current else 'empty'}"
    elif cmd == CommandName.media_pause:
        media = media.model_copy(update={"state": PlayState.paused})
        note = "mpv pause"
    elif cmd == CommandName.media_stop:
        media = media.model_copy(update={"state": PlayState.idle})
        note = "mpv stop"
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
        note = f"mpv next · {head.title}"
    elif cmd == CommandName.media_cassette_on:
        media = media.model_copy(
            update={"cassette": True, "path_label": _path_label(True)}
        )
        note = "cassette on"
    elif cmd == CommandName.media_cassette_off:
        media = media.model_copy(
            update={"cassette": False, "path_label": _path_label(False)}
        )
        note = "cassette off"
    elif cmd == CommandName.media_volume:
        vol = int(p.get("volume", media.volume))
        vol = max(0, min(100, vol))
        media = media.model_copy(update={"volume": vol})
        note = f"volume {vol}"
    else:
        raise HTTPException(status_code=400, detail=f"unhandled command {cmd}")

    board = store.set(board.model_copy(update={"media": media}), detail=note)
    return board, note, media.model_dump(mode="json")
