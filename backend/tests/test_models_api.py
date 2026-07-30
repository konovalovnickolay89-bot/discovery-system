"""Auth boundaries, durable queue, lease/HMAC, public health."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/casual-board-test-data-v2"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret-distinct"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret-distinct"
os.environ["CASUAL_BOARD_UI_PASSWORD"] = "ui-pass-secret"
os.environ["CASUAL_BOARD_SESSION_SECRET"] = "session-hmac-secret"
os.environ["CASUAL_BOARD_ENABLE_AI"] = "true"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ["CASUAL_BOARD_CORS_ORIGINS"] = "https://discovery-system.grok.me"
os.environ["CASUAL_BOARD_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("XAI_API_KEY", None)

from app.config import get_settings
from app.db import close, connect
from app.jobs import get_job, sign_result
from app.main import app
from app.store import reset_store_for_tests


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    close()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def owner():
    return {"Authorization": "Bearer owner-secret-distinct"}


def bridge():
    return {"Authorization": "Bearer bridge-secret-distinct"}


def session(client: TestClient) -> dict:
    r = client.post("/v1/auth/login", json={"password": "ui-pass-secret"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_health_public_minimal(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "data_dir" not in body
    assert "auth_mode" not in body
    assert set(body.keys()) <= {"ok", "service", "version", "time"}


def test_board_requires_session(client: TestClient):
    assert client.get("/v1/board").status_code == 401
    assert client.post("/v1/captures", json={"note": "x"}).status_code == 401
    assert client.post("/v1/chat", json={"message": "status"}).status_code == 401


def test_login_and_board(client: TestClient):
    assert client.post("/v1/auth/login", json={"password": "wrong"}).status_code == 401
    h = session(client)
    r = client.get("/v1/board", headers=h)
    assert r.status_code == 200
    assert "today" in r.json()


def test_owner_token_not_session(client: TestClient):
    assert client.get("/v1/board", headers=owner()).status_code == 401


def test_bridge_token_not_session(client: TestClient):
    assert client.get("/v1/board", headers=bridge()).status_code == 401


def test_capture_session_used_ai_false(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/captures",
        headers=h,
        json={"note": "duck confit allergen check", "use_ai": True},
    )
    assert r.status_code == 200
    assert r.json()["used_ai"] is False


def test_job_survives_db_reconnect(client: TestClient, tmp_path: Path):
    h = session(client)
    r = client.post(
        "/v1/commands",
        headers=h,
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 61, "free_gib": 40, "net": "wired"},
            "source": "web",
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job"]["id"]
    assert r.json()["job"]["status"] == "pending_approval"

    # Simulate process restart: close connection, reconnect same file (no wipe)
    close()
    connect(tmp_path / "casual_board.sqlite3")
    job = get_job(job_id)
    assert job is not None
    assert job.status.value == "pending_approval"


def test_approval_does_not_execute_host(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/commands",
        headers=h,
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 70, "free_gib": 10, "net": "wired"},
            "source": "web",
        },
    )
    job_id = r.json()["job"]["id"]
    assert client.post(f"/v1/actions/{job_id}/approval", json={"approve": True}).status_code == 401
    ok = client.post(
        f"/v1/actions/{job_id}/approval",
        headers=owner(),
        json={"approve": True},
    )
    assert ok.status_code == 200
    assert ok.json()["job"]["status"] == "queued"
    assert client.get("/v1/board", headers=h).json()["machine"]["disk_pct"] != 70


def test_lease_hmac_and_worker_binding(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/commands",
        headers=h,
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 55, "free_gib": 90, "net": "wired", "host": "debian-minimal"},
            "source": "web",
        },
    )
    job_id = r.json()["job"]["id"]
    client.post(f"/v1/actions/{job_id}/approval", headers=owner(), json={"approve": True})

    assert client.get("/v1/bridge/jobs/lease?timeout_s=1").status_code == 401
    assert client.get("/v1/bridge/jobs/lease?timeout_s=1", headers=owner()).status_code == 403

    lease = client.get(
        "/v1/bridge/jobs/lease",
        headers=bridge(),
        params={"worker_id": "worker-a", "timeout_s": 2},
    )
    assert lease.status_code == 200
    job = lease.json()["job"]
    assert job["status"] == "leased"
    nonce = job["lease_nonce"]
    assert nonce

    result = {"stub": True}
    patch = {"machine": {"disk_pct": 55, "free_gib": 90, "net": "wired", "host": "debian-minimal"}}

    bad_w = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "message": "ok",
            "worker_id": "worker-b",
            "lease_nonce": nonce,
            "signature": sign_result(
                job_id=job_id,
                status="completed",
                worker_id="worker-b",
                lease_nonce=nonce,
                result=result,
                message="ok",
                board_patch=patch,
            ),
            "board_patch": patch,
        },
    )
    assert bad_w.status_code == 403

    bad_s = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "worker_id": "worker-a",
            "lease_nonce": nonce,
            "signature": "00" * 32,
            "board_patch": patch,
        },
    )
    assert bad_s.status_code == 401

    sig = sign_result(
        job_id=job_id,
        status="completed",
        worker_id="worker-a",
        lease_nonce=nonce,
        result=result,
        message="ok",
        board_patch=patch,
    )
    good = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "message": "ok",
            "worker_id": "worker-a",
            "lease_nonce": nonce,
            "signature": sig,
            "board_patch": patch,
        },
    )
    assert good.status_code == 200
    assert good.json()["status"] == "completed"
    assert client.get("/v1/board", headers=h).json()["machine"]["disk_pct"] == 55

    replay = client.post(
        "/v1/bridge/jobs/result",
        headers=bridge(),
        json={
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "message": "ok",
            "worker_id": "worker-a",
            "lease_nonce": nonce,
            "signature": sig,
            "board_patch": patch,
        },
    )
    assert replay.status_code in (409, 403)


def test_chat_no_shell(client: TestClient):
    h = session(client)
    r = client.post("/v1/chat", headers=h, json={"message": "rm -rf /"})
    assert r.status_code == 200
    assert "shell" in r.json()["reply"].lower() or "allowlist" in r.json()["reply"].lower()
