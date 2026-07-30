"""Hermes maintainer-agent action handlers (same host as Debian CLI)."""

from __future__ import annotations

from datetime import datetime, timezone

from .agents import meta_dict, run_capture
from .models import (
    HermesAction,
    HermesRequest,
    HermesResponse,
    MachineSection,
    MediaSection,
    TodayItem,
)
from . import store


def handle_hermes(req: HermesRequest) -> HermesResponse:
    action = req.action
    p = req.payload
    agent = req.agent or "hermes"

    if action == HermesAction.ping:
        return HermesResponse(
            action=action,
            message="pong",
            board=store.get_board(),
            meta={**store.snapshot_meta(), **meta_dict()},
        )

    if action == HermesAction.status:
        b = store.get_board()
        return HermesResponse(
            action=action,
            message=b.header.status.label,
            board=b,
            meta=store.snapshot_meta(),
        )

    if action == HermesAction.reset_board:
        b = store.reset_board(source=agent)
        return HermesResponse(action=action, message="board reset", board=b)

    if action == HermesAction.set_machine:
        cur = store.get_board()
        m = cur.machine.model_dump()
        m.update({k: v for k, v in p.items() if k in MachineSection.model_fields})
        machine = MachineSection.model_validate(m).with_health()
        board = store.set_board(
            cur.model_copy(update={"machine": machine}),
            source=agent,
            kind="machine",
            detail="hermes set_machine",
        )
        return HermesResponse(action=action, message="machine updated", board=board)

    if action == HermesAction.add_today:
        cur = store.get_board()
        item = TodayItem.model_validate(
            {
                "id": p.get("id") or f"t-{int(datetime.now(timezone.utc).timestamp())}",
                "text": p.get("text") or p.get("body") or "note",
                "kind": p.get("kind") or "capture",
                "tags": p.get("tags") or ["capture"],
                "level": p.get("level") or "info",
            }
        )
        items = list(cur.today.items) + [item]
        board = store.set_board(
            cur.model_copy(update={"today": cur.today.model_copy(update={"items": items})}),
            source=agent,
            kind="today",
            detail=f"add {item.id}",
        )
        return HermesResponse(action=action, message=f"added {item.id}", board=board)

    if action == HermesAction.remove_today:
        cur = store.get_board()
        tid = str(p.get("id") or "")
        items = [i for i in cur.today.items if i.id != tid]
        board = store.set_board(
            cur.model_copy(update={"today": cur.today.model_copy(update={"items": items})}),
            source=agent,
            kind="today",
            detail=f"remove {tid}",
        )
        return HermesResponse(action=action, message=f"removed {tid}", board=board)

    if action == HermesAction.set_media:
        cur = store.get_board()
        m = cur.media.model_dump()
        m.update({k: v for k, v in p.items() if k in MediaSection.model_fields})
        media = MediaSection.model_validate(m)
        board = store.patch_media(media, source=agent, detail="hermes set_media")
        return HermesResponse(action=action, message="media updated", board=board)

    if action == HermesAction.capture:
        note = str(p.get("note") or p.get("text") or "").strip()
        if not note:
            return HermesResponse(ok=False, action=action, message="note required")
        draft = run_capture(note)
        cur = store.get_board()
        item = TodayItem(
            id=f"cap-{int(datetime.now(timezone.utc).timestamp())}",
            text=f"{draft.title} — {draft.body}",
            kind="capture",
            tags=draft.tags,
            level=draft.level,
        )
        items = list(cur.today.items) + [item]
        board = store.set_board(
            cur.model_copy(update={"today": cur.today.model_copy(update={"items": items})}),
            source=agent,
            kind="capture",
            detail=draft.title,
        )
        return HermesResponse(
            action=action,
            message=draft.title,
            board=board,
            meta={"draft": draft.model_dump(mode="json")},
        )

    return HermesResponse(ok=False, action=action, message=f"unknown action {action}")
