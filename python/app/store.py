"""Board store: file-backed state + event fan-out for CLI / web / Hermes."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import Board, BoardEvent, MediaSection
from .seed import build_board

# On Debian set CASUAL_BOARD_DATA=/var/lib/casual-board/board.json
_DEFAULT_DATA = Path(os.environ.get("CASUAL_BOARD_DATA", "/tmp/casual-board-board.json"))

_lock = threading.RLock()
_board: Board | None = None
_seq = 0
_listeners: list[Callable[[BoardEvent], None]] = []
_async_queues: list[asyncio.Queue[BoardEvent]] = []


def data_path() -> Path:
    return Path(os.environ.get("CASUAL_BOARD_DATA", str(_DEFAULT_DATA)))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(board: Board) -> Board:
    return board.model_copy(
        update={"header": board.header.model_copy(update={"updated_at": _now()})}
    )


def _persist(board: Board) -> None:
    path = data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(board.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def _load() -> Board:
    path = data_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return Board.model_validate(raw)
        except Exception:  # noqa: BLE001
            pass
    board = build_board()
    _persist(board)
    return board


def get_board() -> Board:
    global _board
    with _lock:
        if _board is None:
            _board = _load()
        return _board


def set_board(board: Board, *, source: str, kind: str, detail: str = "") -> Board:
    """Replace board, persist, emit event."""
    global _board, _seq
    with _lock:
        board = _stamp(board)
        _board = board
        _persist(board)
        _seq += 1
        event = BoardEvent(
            seq=_seq,
            kind=kind,
            source=source,
            detail=detail,
            at=_now(),
            board=board,
        )
    _emit(event)
    return board


def patch_media(media: MediaSection, *, source: str, detail: str = "") -> Board:
    b = get_board()
    return set_board(
        b.model_copy(update={"media": media}),
        source=source,
        kind="media",
        detail=detail,
    )


def reset_board(*, source: str = "admin") -> Board:
    return set_board(build_board(), source=source, kind="reset", detail="seed restored")


def subscribe_sync(fn: Callable[[BoardEvent], None]) -> Callable[[], None]:
    _listeners.append(fn)

    def unsub() -> None:
        if fn in _listeners:
            _listeners.remove(fn)

    return unsub


def subscribe_async() -> asyncio.Queue[BoardEvent]:
    q: asyncio.Queue[BoardEvent] = asyncio.Queue(maxsize=64)
    _async_queues.append(q)
    return q


def unsubscribe_async(q: asyncio.Queue[BoardEvent]) -> None:
    if q in _async_queues:
        _async_queues.remove(q)


def _emit(event: BoardEvent) -> None:
    for fn in list(_listeners):
        try:
            fn(event)
        except Exception:  # noqa: BLE001
            pass
    for q in list(_async_queues):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                _ = q.get_nowait()
            except Exception:  # noqa: BLE001
                pass
            try:
                q.put_nowait(event)
            except Exception:  # noqa: BLE001
                pass


def seq() -> int:
    return _seq


def snapshot_meta() -> dict[str, Any]:
    return {
        "seq": _seq,
        "data_path": str(data_path()),
        "updated_at": get_board().header.updated_at.isoformat(),
    }
