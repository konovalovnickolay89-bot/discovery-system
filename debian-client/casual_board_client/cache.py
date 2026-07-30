"""Local last-known-good snapshot cache (offline CLI)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import BoardSnapshot

DEFAULT_CACHE = Path(
    os.environ.get(
        "CASUAL_BOARD_CACHE",
        str(Path.home() / ".cache" / "casual-board" / "last_board.json"),
    )
)


class SnapshotCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CACHE

    def save(self, board: BoardSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(board.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> BoardSnapshot | None:
        if not self.path.is_file():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return BoardSnapshot.model_validate(raw)
        except Exception:  # noqa: BLE001
            return None
