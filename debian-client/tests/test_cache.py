from pathlib import Path

from casual_board_client.cache import SnapshotCache
from casual_board_client.models import BoardSnapshot


def test_cache_roundtrip(tmp_path: Path):
    cache = SnapshotCache(tmp_path / "board.json")
    snap = BoardSnapshot(meta={"revision": 7, "status": {"label": "ok · quiet"}})
    cache.save(snap)
    loaded = cache.load()
    assert loaded is not None
    assert loaded.revision == 7
    assert loaded.status_label == "ok · quiet"
