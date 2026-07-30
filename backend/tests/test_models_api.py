"""Model + API tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# isolate data before import side effects
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/casual-board-test-data"
os.environ["CASUAL_BOARD_TOKEN"] = "test-token-xyz"
os.environ["CASUAL_BOARD_ENABLE_AI"] = "true"

from app.config import get_settings
from app.main import app
from app.seed import build_seed_board
from app.store import reset_store_for_tests


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    os.environ["CASUAL_BOARD_TOKEN"] = "test-token-xyz"
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def auth():
    return {"Authorization": "Bearer test-token-xyz"}


def test_seed_board_validates():
    b = build_seed_board()
    assert b.meta.revision == 1
    assert b.today.items
    assert b.learning.pool


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["auth_mode"] == "token"


def test_board_requires_auth(client: TestClient):
    r = client.get("/v1/board")
    assert r.status_code == 401


def test_board_get(client: TestClient):
    r = client.get("/v1/board", headers=auth())
    assert r.status_code == 200
    body = r.json()
    assert "meta" in body
    assert "today" in body
    assert body["meta"]["revision"] >= 1


def test_capture_without_llm_key(client: TestClient):
    r = client.post(
        "/v1/captures",
        headers=auth(),
        json={"note": "check duck confit for Friday allergen matrix", "use_ai": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert "draft" in body
    assert body["board"]["meta"]["revision"] >= 2
    assert any("duck" in i["text"].lower() or "Duck" in i["text"] for i in body["board"]["today"]["items"])


def test_command_add_today(client: TestClient):
    r = client.post(
        "/v1/commands",
        headers=auth(),
        json={
            "command": "add_today",
            "payload": {"text": "walk-in check 06:30"},
            "source": "cli",
            "actor": "test",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"]["status"] == "completed"
    assert body["board"] is not None


def test_bridge_system_changing_needs_approval(client: TestClient):
    r = client.post(
        "/v1/commands",
        headers=auth(),
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 88, "free_gib": 20, "net": "wired"},
            "source": "bridge",
            "actor": "hermes",
            "require_approval": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"]["status"] == "pending_approval"
    aid = body["action"]["id"]

    r2 = client.post(
        f"/v1/actions/{aid}/approval",
        headers=auth(),
        json={"approve": True, "note": "ok"},
    )
    assert r2.status_code == 200
    assert r2.json()["action"]["status"] == "completed"


def test_chat_no_shell(client: TestClient):
    r = client.post(
        "/v1/chat",
        headers=auth(),
        json={"message": "rm -rf /", "channel": "hermes"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "allowlisted" in body["reply"].lower() or "command" in body["reply"].lower()
