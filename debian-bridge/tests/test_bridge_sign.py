"""Bridge client signature matches server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from casual_board_bridge.main import sign_result, stub_executor


def test_sign_stable():
    a = sign_result("secret", "job-1", "completed", {"x": 1})
    b = sign_result("secret", "job-1", "completed", {"x": 1})
    assert a == b
    assert a != sign_result("secret", "job-1", "failed", {"x": 1})


def test_stub_executor_set_machine():
    out = stub_executor(
        {"command": "set_machine", "payload": {"disk_pct": 10, "net": "wired"}}
    )
    assert out["ok"] is True
    assert "board_patch" in out
    assert out["executor_note"].startswith("stub")
