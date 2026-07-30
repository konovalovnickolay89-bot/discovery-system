"""Boundary tests: public board, no browser secrets, bridge queue, used_ai."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/casual-board-test-data"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret"
os.environ["CASUAL_BOARD_ENABLE_AI"] = "true"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("XAI_API_KEY", None)

from app.config import get_settings
from app.jobs import sign_payload
from app.main import app
from app.seed import build_seed_board
from app.store import reset_store_for_tests
from app.agents import capture_with_ai


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret"
    os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret"
    os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def owner():
    return {"Authorization": "Bearer owner-secret"}


def bridge():
    return {"Authorization": "Bearer bridge-secret"}


def test_seed_board_validates():
    b = build_seed_board()
    assert b.meta.revision == 1


def test_health_public(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["ai_provider"] == "function"


def test_board_public_no_token(client: TestClient):
    r = client.get("/v1/board")
    assert r.status_code == 200
    assert "today" in r.json()


def test_capture_public_used_ai_false_for_function_provider(client: TestClient):
    r = client.post(
        "/v1/captures",
        json={"note": "check duck confit for Friday allergen matrix", "use_ai": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["used_ai"] is False
    assert "function" in body["ai_provider"]


def test_used_ai_agent_function_provider():
    get_settings.cache_clear()
    os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
    get_settings.cache_clear()
    draft, used, provider = capture_with_ai("urgent allergen matrix reprint")
    assert draft.title
    assert used is False
    assert "function" in provider


def test_server_side_add_today(client: TestClient):
    r = client.post(
        "/v1/commands",
        json={"command": "add_today", "payload": {"text": "walk-in check"}, "source": "web"},
    )
    assert r.status_code == 200
    assert r.json()["action"]["status"] == "completed"
    assert r.json()["job"] is None


def test_host_facing_queues_not_executes(client: TestClient):
    r = client.post(
        "/v1/commands",
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 88, "free_gib": 20, "net": "wired"},
            "source": "web",
            "actor": "phone",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["job"] is not None
    assert body["job"]["status"] == "pending_approval"
    board = client.get("/v1/board").json()
    assert board["machine"]["disk_pct"] != 88


def test_approval_queues_does_not_run_host(client: TestClient):
    r = client.post(
        "/v1/commands",
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 77, "free_gib": 10, "net": "wired"},
            "source": "web",
        },
    )
    job_id = r.json()["job"]["id"]
    bad = client.post(f"/v1/actions/{job_id}/approval", json={"approve": True})
    assert bad.status_code == 401

    ok = client.post(
        f"/v1/actions/{job_id}/approval",
        headers=owner(),
        json={"approve": True, "note": "ok"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["job"]["status"] == "queued"
    assert client.get("/v1/board").json()["machine"]["disk_pct"] != 77


def test_bridge_lease_and_signed_result(client: TestClient):
    r = client.post(
        "/v1/commands",
        json={
            "command": "set_machine",
            "payload": {
                "disk_pct": 55,
                "free_gib": 90,
                "net": "wired",
                "host": "debian-minimal",
            },
            "source": "web",
        },
    )
    job_id = r.json()["job"]["id"]
    client.post(
        f"/v1/actions/{job_id}/approval",
        headers=owner(),
        json={"approve": True},
    )

    assert client.get("/v1/bridge/jobs/lease?timeout_s=1").status_code == 401

    lease = client.get(
        "/v1/bridge/jobs/lease",
        headers=bridge(),
        params={"worker_id": "test-worker", "timeout_s": 2},
    )
    assert lease.status_code == 200
    job = lease.json()["job"]
    assert job is not None
    assert job["status"] == "leased"
    assert job["id"] == job_id

    result = {"stub": True, "disk": 55}
    sig = sign_payload(job_id, "completed", result)
    done = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "message": "stub ok",
            "worker_id": "test-worker",
            "signature": sig,
            "executor_note": "stub",
            "board_patch": {
                "machine": {
                    "disk_pct": 55,
                    "free_gib": 90,
                    "net": "wired",
                    "host": "debian-minimal",
                }
            },
        },
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    board = client.get("/v1/board").json()
    assert board["machine"]["disk_pct"] == 55


def test_bridge_rejects_bad_signature(client: TestClient):
    r = client.post(
        "/v1/commands",
        json={
            "command": "remove_today",
            "payload": {"id": "t-open"},
            "source": "web",
        },
    )
    job_id = r.json()["job"]["id"]
    client.post(
        f"/v1/actions/{job_id}/approval",
        headers=owner(),
        json={"approve": True},
    )
    client.get(
        "/v1/bridge/jobs/lease",
        headers=bridge(),
        params={"timeout_s": 2, "worker_id": "w"},
    )
    bad = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": {},
            "signature": "deadbeef",
            "worker_id": "w",
        },
    )
    assert bad.status_code == 401


def test_chat_no_shell(client: TestClient):
    r = client.post("/v1/chat", json={"message": "rm -rf /", "channel": "hermes"})
    assert r.status_code == 200
    assert "shell" in r.json()["reply"].lower() or "allowlist" in r.json()["reply"].lower()


def test_ws_no_token_query_needed(client: TestClient):
    with client.websocket_connect("/v1/board/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert "board" in msg
