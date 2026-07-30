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


def test_blank_board_factory():
    from app.seed import build_blank_board

    b = build_blank_board()
    assert b.today.items == []
    assert b.briefing.pins == []
    assert b.briefing.ring == []
    assert b.learning.pool == []
    assert b.media.current is None
    assert b.media.queue == []
    assert b.media.state.value == "idle"
    assert "awaiting" in (b.machine.detail or "").lower() or "awaiting" in b.machine.host
    assert "chicken" not in b.model_dump_json().lower()
    assert "show hn" not in b.model_dump_json().lower()


def test_start_fresh_requires_auth_and_phrase(client: TestClient, tmp_path: Path):
    # unauthenticated
    r = client.post("/v1/board/start-fresh", json={"confirmation": "START FRESH"})
    assert r.status_code == 401

    h = session(client)
    # wrong phrase
    bad = client.post("/v1/board/start-fresh", headers=h, json={"confirmation": "please"})
    assert bad.status_code == 400

    # seed some content via capture
    client.post(
        "/v1/captures",
        headers=h,
        json={"note": "real capture to wipe", "use_ai": False},
    )
    before = client.get("/v1/board", headers=h).json()
    assert len(before["today"]["items"]) >= 1
    rev_before = before["meta"]["revision"]

    # queue a host job so we can assert jobs preserved
    job_r = client.post(
        "/v1/commands",
        headers=h,
        json={
            "command": "set_machine",
            "payload": {"disk_pct": 10, "free_gib": 1, "net": "wired"},
            "source": "web",
        },
    )
    job_id = job_r.json()["job"]["id"]

    # write a fake action line (audit)
    actions = tmp_path / "actions.jsonl"
    actions.write_text('{"id":"act-keep","command":"status","status":"completed","source":"web","actor":"t","payload":{},"created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")

    ok = client.post(
        "/v1/board/start-fresh",
        headers=h,
        json={"confirmation": "START FRESH"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    board = body["board"]
    assert board["today"]["items"] == []
    assert board["briefing"]["pins"] == []
    assert board["briefing"]["ring"] == []
    assert board["learning"]["pool"] == []
    assert board["media"]["current"] is None
    assert board["media"]["queue"] == []
    assert board["meta"]["revision"] > rev_before
    assert "chicken" not in str(board).lower()
    assert body["backup_path"]
    assert Path(body["backup_path"]).is_file()

    # jobs preserved
    from app.jobs import get_job

    assert get_job(job_id) is not None
    # audit file still present
    assert actions.is_file()
    assert "act-keep" in actions.read_text()


def test_seed_reset_blocked_or_dev_only(client: TestClient):
    assert client.post("/v1/admin/reset-seed").status_code == 401
    r = client.post("/v1/admin/reset-seed", headers=owner())
    assert r.status_code == 200
    assert len(r.json()["today"]["items"]) > 0

    import os
    from app.config import get_settings
    from app.store import get_store

    os.environ["CASUAL_BOARD_ENV"] = "production"
    get_settings.cache_clear()
    try:
        raised = False
        try:
            get_store().reset_to_seed_dev_only()
        except RuntimeError:
            raised = True
        assert raised, "seed reset must raise in production"
        assert client.post("/v1/admin/reset-seed", headers=owner()).status_code == 403
    finally:
        os.environ["CASUAL_BOARD_ENV"] = "development"
        get_settings.cache_clear()


def test_evolving_cook_requires_session(client: TestClient):
    r = client.post(
        "/v1/evolving-cook",
        json={
            "available": "onion",
            "traceability": "labelled_chilled_known",
            "where_for": "staff_meal",
        },
    )
    assert r.status_code == 401


def test_evolving_cook_guest_exposed_discard(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/evolving-cook",
        headers=h,
        json={
            "available": "roast potatoes, gravy",
            "traceability": "guest_exposed_buffet",
            "where_for": "a_la_carte",
            "allergens": "gluten, milk",
            "desired_outcome": "special",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["verdict"] == "discard_or_escalate"
    assert body["guest_service_allowed"] is False
    assert any("guest" in n.lower() or "never" in n.lower() for n in body.get("notes", []))
    assert body["allergen_prompts"]
    for route in body["routes"]:
        assert route["guest_service"] is False


def test_evolving_cook_unknown_high_risk_discard(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/evolving-cook",
        headers=h,
        json={
            "available": "chicken trim, cooked rice",
            "traceability": "unknown",
            "where_for": "banqueting",
            "allergens": "",
            "desired_outcome": "staff pie",
        },
    )
    assert r.status_code == 200
    assert r.json()["decision"]["verdict"] == "discard_or_escalate"
    assert r.json()["guest_service_allowed"] is False


def test_evolving_cook_safe_labelled_routes(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/evolving-cook",
        headers=h,
        json={
            "available": "onion ends, carrot peel, herb stalks",
            "traceability": "labelled_chilled_known",
            "where_for": "staff_meal",
            "allergens": "celery",
            "desired_outcome": "clear soup",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["verdict"] == "proceed"
    assert len(body["routes"]) == 3
    titles = {x["title"] for x in body["routes"]}
    assert "Classic route" in titles
    assert "New direction" in titles
    assert "Small experiment" in titles
    assert body["do_this_next"]
    assert body["sort_tray"]
    assert any("celery" in p.lower() for p in body["allergen_prompts"])


def test_evolving_cook_allergen_prompts(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/evolving-cook",
        headers=h,
        json={
            "available": "bread trim",
            "traceability": "labelled_chilled_known",
            "where_for": "breakfast",
            "allergens": "gluten, sesame",
            "desired_outcome": "croutons",
        },
    )
    assert r.status_code == 200
    prompts = " ".join(r.json()["allergen_prompts"]).lower()
    assert "gluten" in prompts
    assert "sesame" in prompts
