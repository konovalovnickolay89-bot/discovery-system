"""Versioned persistent board state + async event fan-out."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Settings, get_settings
from .models import ActionRecord, Board, BoardStatus, Level, StreamEvent
from .seed import build_seed_board

log = logging.getLogger("casual_board.store")


class BoardStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.RLock()
        self._board: Board | None = None
        self._actions: dict[str, ActionRecord] = {}
        self._listeners: list[Callable[[StreamEvent], None]] = []
        self._async_queues: list[asyncio.Queue[StreamEvent]] = []
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _recompute_status(self, board: Board) -> Board:
        warnings = sum(1 for i in board.today.items if i.level == Level.warn)
        if board.machine.warn:
            warnings += 1
        status = (
            BoardStatus(
                label=f"worth a look — {warnings} warnings",
                warnings=warnings,
            )
            if warnings
            else BoardStatus(label="ok · quiet", warnings=0)
        )
        meta = board.meta.model_copy(update={"status": status})
        return board.model_copy(update={"meta": meta})

    def _persist_board(self, board: Board) -> None:
        path = self.settings.board_path
        tmp = path.with_suffix(".tmp")
        tmp.write_text(board.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def _append_action(self, action: ActionRecord) -> None:
        path = self.settings.actions_path
        with path.open("a", encoding="utf-8") as f:
            f.write(action.model_dump_json() + "\n")

    def _load(self) -> Board:
        path = self.settings.board_path
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return Board.model_validate(raw)
            except Exception as e:  # noqa: BLE001
                log.warning("board load failed, reseeding: %s", e)
        board = build_seed_board()
        self._persist_board(board)
        return board

    def get(self) -> Board:
        with self._lock:
            if self._board is None:
                self._board = self._load()
            return self._board

    def set(
        self,
        board: Board,
        *,
        bump: bool = True,
        detail: str = "",
    ) -> Board:
        with self._lock:
            board = self._recompute_status(board)
            now = self._now()
            rev = board.meta.revision + (1 if bump else 0)
            meta = board.meta.model_copy(update={"revision": rev, "updated_at": now})
            board = board.model_copy(update={"meta": meta})
            self._board = board
            self._persist_board(board)
            event = StreamEvent(
                type="revision",
                revision=rev,
                at=now,
                board=board,
                detail=detail or None,
            )
        self._emit(event)
        log.info("board revision=%s detail=%s", rev, detail)
        return board

    def save_action(self, action: ActionRecord) -> ActionRecord:
        with self._lock:
            self._actions[action.id] = action
            self._append_action(action)
        event = StreamEvent(
            type="action",
            revision=self.get().meta.revision,
            at=action.updated_at,
            action=action,
            detail=action.message or None,
        )
        self._emit(event)
        return action

    def get_action(self, action_id: str) -> ActionRecord | None:
        with self._lock:
            if action_id in self._actions:
                return self._actions[action_id]
        # fallback scan jsonl
        path = self.settings.actions_path
        if not path.is_file():
            return None
        found: ActionRecord | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = ActionRecord.model_validate_json(line)
            except Exception:  # noqa: BLE001
                continue
            if rec.id == action_id:
                found = rec
        if found:
            with self._lock:
                self._actions[action_id] = found
        return found

    def reset(self) -> Board:
        return self.set(build_seed_board(), bump=True, detail="reset to seed")

    def subscribe_async(self) -> asyncio.Queue[StreamEvent]:
        q: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=128)
        self._async_queues.append(q)
        return q

    def unsubscribe_async(self, q: asyncio.Queue[StreamEvent]) -> None:
        if q in self._async_queues:
            self._async_queues.remove(q)

    def _emit(self, event: StreamEvent) -> None:
        for fn in list(self._listeners):
            try:
                fn(event)
            except Exception:  # noqa: BLE001
                pass
        for q in list(self._async_queues):
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


_store: BoardStore | None = None


def get_store() -> BoardStore:
    global _store
    if _store is None:
        _store = BoardStore()
    return _store


def reset_store_for_tests(tmp_path: Path) -> BoardStore:
    global _store
    settings = get_settings().model_copy(update={"data_dir": tmp_path})
    _store = BoardStore(settings)
    return _store
