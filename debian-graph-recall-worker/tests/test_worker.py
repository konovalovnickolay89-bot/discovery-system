"""Graph Recall worker tests — fake Hermes only, no model calls."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/gr-worker-test"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret-distinct"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret-distinct"
os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
os.environ["CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S"] = "300"
os.environ["CASUAL_BOARD_UI_PASSWORD"] = "ui-pass-secret"
os.environ["CASUAL_BOARD_SESSION_SECRET"] = "session-hmac-secret"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ["CASUAL_BOARD_CORS_ORIGINS"] = "https://discovery-system.grok.me"
os.environ["CASUAL_BOARD_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import get_settings
from app.db import close
from app.graph_recall_queue import reap_expired_leases, sign_result
from app.main import app
from app.store import reset_store_for_tests
from casual_board_graph_recall_worker import RESTRICTED_TOOLSET
from casual_board_graph_recall_worker.client import GraphRecallClient, sign_result as client_sign
from casual_board_graph_recall_worker.hermes_runner import (
    build_hermes_command,
    filter_kitchen_memory,
    validate_logseq_path,
)
from casual_board_graph_recall_worker.prompt import build_prompt
from casual_board_graph_recall_worker.worker import GraphRecallWorker


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    close()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
    os.environ["CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S"] = "300"
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def session(client: TestClient) -> dict:
    r = client.post("/v1/auth/login", json={"password": "ui-pass-secret"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def gr_headers():
    return {"Authorization": "Bearer graph-recall-secret"}


def create_safe_consult(client: TestClient) -> str:
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "build",
            "ingredients_or_problem": "onion, carrot",
            "traceability": "labelled_chilled_known",
            "service_context": "staff_meal",
            "request_graph_recall": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_recall_status"] == "queued"
    return r.json()["id"]


def test_build_hermes_command_uses_restricted_toolset():
    cmd = build_hermes_command(240)
    assert cmd[0] == "hermes"
    assert "-z" in cmd
    assert "--toolset" in cmd
    assert RESTRICTED_TOOLSET in cmd
    assert "--yolo" not in cmd


def test_prompt_preserves_local_safety_and_delimits_data():
    payload = {
        "consultation": {
            "id": "cook-1",
            "mode": "rescue",
            "ingredients_or_problem": "buffet leftovers",
            "local_safety_plan": {
                "rejected": True,
                "decision": {"verdict": "discard_or_escalate", "title": "stop"},
                "guest_service_allowed": False,
            },
        },
        "mode_contract": "strategic_application_strict_safety",
        "rules": ["Never override local safety"],
        "produce_lots": [],
        "ingredients": [],
        "dish": None,
    }
    p = build_prompt(payload)
    assert "UNTRUSTED_DATA_JSON" in p
    assert "untrusted data" in p.lower() or "never executable" in p.lower()
    assert "discard_or_escalate" in p
    assert "local_safety_rejected" in p
    assert "true" in p.lower()


def test_invalid_logseq_paths_omitted(tmp_path: Path):
    root = tmp_path / "graph"
    root.mkdir()
    good = root / "onion.md"
    good.write_text("notes")
    items = [
        {"title": "good", "path": str(good), "finding": "x"},
        {"title": "bad", "path": "/etc/passwd", "finding": "no"},
        {"title": "nopath", "path": "", "finding": "no"},
    ]
    out = filter_kitchen_memory(items, graph_root=str(root))
    assert len(out) == 1
    assert out[0]["title"] == "good"
    assert not validate_logseq_path("/etc/passwd", str(root))


def test_no_job_available(client: TestClient):
    r = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "graph-recall@test", "timeout_s": 1},
    )
    assert r.status_code == 200
    assert r.json()["job"] is None


def test_once_signed_completed_with_fake_hermes(client: TestClient, tmp_path: Path):
    cid = create_safe_consult(client)
    # Fake HTTP via TestClient adapter
    class TCClient(GraphRecallClient):
        def lease(self, timeout_s: float = 25.0):
            r = client.get(
                "/v1/graph-recall/jobs/lease",
                headers=gr_headers(),
                params={"worker_id": self.worker_id, "timeout_s": timeout_s},
            )
            r.raise_for_status()
            return r.json().get("job")

        def post_result(self, **kwargs):
            # sign with same token
            from casual_board_graph_recall_worker.client import sign_result as sr

            body = {
                "consultation_id": kwargs["consultation_id"],
                "status": kwargs["status"],
                "kitchen_memory": kwargs.get("kitchen_memory") or [],
                "enrichment": kwargs.get("enrichment") or {},
                "message": kwargs.get("message") or "",
                "worker_id": self.worker_id,
                "lease_nonce": kwargs["lease_nonce"],
                "signature": sr(
                    self.token,
                    consultation_id=kwargs["consultation_id"],
                    status=kwargs["status"],
                    worker_id=self.worker_id,
                    lease_nonce=kwargs["lease_nonce"],
                    kitchen_memory=kwargs.get("kitchen_memory") or [],
                    enrichment=kwargs.get("enrichment") or {},
                    message=kwargs.get("message") or "",
                ),
                "proposed_guest_service": kwargs.get("proposed_guest_service"),
            }
            r = client.post("/v1/graph-recall/jobs/result", headers=gr_headers(), json=body)
            r.raise_for_status()
            return r.json()

    graph = tmp_path / "Logseq" / "graph"
    graph.mkdir(parents=True)
    note = graph / "stock.md"
    note.write_text("onion stock")

    def fake_hermes(prompt: str, meta: dict) -> str:
        assert "--toolset" in meta["command"]
        assert RESTRICTED_TOOLSET in meta["command"]
        return json.dumps(
            {
                "kitchen_memory": [
                    {
                        "title": "Onion stock",
                        "path": str(note),
                        "relevance": "stock",
                        "finding": "Brown gently",
                    },
                    {
                        "title": "Fake",
                        "path": "/tmp/not-logseq.md",
                        "relevance": "x",
                        "finding": "should drop",
                    },
                ],
                "enrichment": {"note": "keep it simple", "primary_plan": {"summary": "soffritto base"}},
                "meta": {"model": "fake", "provider": "test"},
            }
        )

    # patch filter root via monkey by writing valid path under LOGSEQ - use filter in runner with default;
    # for test, use path that validate_logseq_path accepts if parent exists under default root — instead
    # patch filter by using path under /home/... that doesn't exist — adjust fake to only valid if we
    # monkeypatch LOGSEQ root in filter call. Simpler: set path to note and monkeypatch module root.
    import casual_board_graph_recall_worker.hermes_runner as hr

    old = hr.LOGSEQ_GRAPH_ROOT
    hr.LOGSEQ_GRAPH_ROOT = str(graph)
    try:
        w = GraphRecallWorker(
            TCClient("http://testserver", "graph-recall-secret", "graph-recall@test"),
            hermes_runner=fake_hermes,
        )
        res = w.once()
        assert res is not None
        assert res["graph_recall_status"] == "completed"
        assert res["task_status"] == "kitchen_memory_returned"
        mem = res["local_safety_plan"]["kitchen_memory"]
        assert any(m["title"] == "Onion stock" for m in mem)
        assert not any(m["title"] == "Fake" for m in mem)
    finally:
        hr.LOGSEQ_GRAPH_ROOT = old


def test_malformed_hermes_signed_failed(client: TestClient):
    create_safe_consult(client)

    class TCClient(GraphRecallClient):
        def lease(self, timeout_s: float = 25.0):
            r = client.get(
                "/v1/graph-recall/jobs/lease",
                headers=gr_headers(),
                params={"worker_id": self.worker_id, "timeout_s": 2},
            )
            return r.json().get("job")

        def post_result(self, **kwargs):
            from casual_board_graph_recall_worker.client import sign_result as sr

            body = {
                "consultation_id": kwargs["consultation_id"],
                "status": kwargs["status"],
                "kitchen_memory": [],
                "enrichment": {},
                "message": kwargs.get("message") or "",
                "worker_id": self.worker_id,
                "lease_nonce": kwargs["lease_nonce"],
                "signature": sr(
                    self.token,
                    consultation_id=kwargs["consultation_id"],
                    status=kwargs["status"],
                    worker_id=self.worker_id,
                    lease_nonce=kwargs["lease_nonce"],
                    kitchen_memory=[],
                    enrichment={},
                    message=kwargs.get("message") or "",
                ),
            }
            r = client.post("/v1/graph-recall/jobs/result", headers=gr_headers(), json=body)
            r.raise_for_status()
            return r.json()

    def bad_hermes(prompt: str, meta: dict) -> str:
        return "not-json at all {{"

    w = GraphRecallWorker(
        TCClient("http://testserver", "graph-recall-secret", "graph-recall@test"),
        hermes_runner=bad_hermes,
    )
    res = w.once()
    assert res["graph_recall_status"] == "failed"
    # consultation not lost — still readable
    h = session(client)
    # find from list
    items = client.get("/v1/cook/consultations", headers=h).json()
    assert any(i["id"] == res["id"] for i in items)


def test_wrong_token_signature_worker_nonce(client: TestClient):
    cid = create_safe_consult(client)
    lease = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "w1", "timeout_s": 2},
    ).json()["job"]
    nonce = lease["lease_nonce"]

    assert client.get("/v1/graph-recall/jobs/lease", params={"timeout_s": 1}).status_code == 401

    enrichment = {"note": "x"}
    good_sig = sign_result(
        consultation_id=cid,
        status="completed",
        worker_id="w1",
        lease_nonce=nonce,
        kitchen_memory=[],
        enrichment=enrichment,
        message="ok",
    )
    # wrong worker
    assert (
        client.post(
            "/v1/graph-recall/jobs/result",
            headers=gr_headers(),
            json={
                "consultation_id": cid,
                "status": "completed",
                "worker_id": "other",
                "lease_nonce": nonce,
                "signature": sign_result(
                    consultation_id=cid,
                    status="completed",
                    worker_id="other",
                    lease_nonce=nonce,
                    kitchen_memory=[],
                    enrichment={},
                    message="ok",
                ),
                "kitchen_memory": [],
                "enrichment": {},
                "message": "ok",
            },
        ).status_code
        == 403
    )
    # wrong sig
    assert (
        client.post(
            "/v1/graph-recall/jobs/result",
            headers=gr_headers(),
            json={
                "consultation_id": cid,
                "status": "completed",
                "worker_id": "w1",
                "lease_nonce": nonce,
                "signature": "00" * 32,
                "kitchen_memory": [],
                "enrichment": {},
            },
        ).status_code
        == 401
    )
    # complete once
    assert (
        client.post(
            "/v1/graph-recall/jobs/result",
            headers=gr_headers(),
            json={
                "consultation_id": cid,
                "status": "completed",
                "worker_id": "w1",
                "lease_nonce": nonce,
                "signature": good_sig,
                "kitchen_memory": [],
                "enrichment": enrichment,
                "message": "ok",
            },
        ).status_code
        == 200
    )
    # replay nonce
    assert (
        client.post(
            "/v1/graph-recall/jobs/result",
            headers=gr_headers(),
            json={
                "consultation_id": cid,
                "status": "completed",
                "worker_id": "w1",
                "lease_nonce": nonce,
                "signature": good_sig,
                "kitchen_memory": [],
                "enrichment": enrichment,
                "message": "ok",
            },
        ).status_code
        in (409, 403)
    )


def test_lease_expiry_requeues_and_blocks_stale_completion(client: TestClient):
    cid = create_safe_consult(client)
    # Force short lease for this test by updating DB after lease
    lease = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "w-expire", "timeout_s": 2},
    ).json()["job"]
    assert lease
    nonce = lease["lease_nonce"]
    from app.db import get_conn
    from datetime import datetime, timezone, timedelta

    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    get_conn().execute(
        "UPDATE graph_recall_jobs SET lease_expires_at=? WHERE consultation_id=? AND status='leased'",
        (past, cid),
    )
    get_conn().commit()

    n = reap_expired_leases()
    assert n >= 1
    h = session(client)
    c = client.get(f"/v1/cook/consultations/{cid}", headers=h).json()
    assert c["graph_recall_status"] == "queued"
    assert c["task_status"] == "kitchen_memory_queued"
    assert any(a.get("event") == "kitchen_memory_lease_expired" for a in c["audit"])

    # stale completion rejected
    sig = sign_result(
        consultation_id=cid,
        status="completed",
        worker_id="w-expire",
        lease_nonce=nonce,
        kitchen_memory=[],
        enrichment={},
        message="late",
    )
    late = client.post(
        "/v1/graph-recall/jobs/result",
        headers=gr_headers(),
        json={
            "consultation_id": cid,
            "status": "completed",
            "worker_id": "w-expire",
            "lease_nonce": nonce,
            "signature": sig,
            "kitchen_memory": [],
            "enrichment": {},
            "message": "late",
        },
    )
    assert late.status_code in (409, 403)


def test_blocked_local_safety_not_overridden_by_memory(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "rescue",
            "ingredients_or_problem": "buffet",
            "traceability": "guest_exposed_buffet",
            "service_context": "a_la_carte",
            "request_graph_recall": True,
        },
    )
    body = r.json()
    assert body["task_status"] == "blocked"
    assert body["graph_recall_status"] == "not_requested"
    assert body["local_safety_plan"]["rejected"] is True


def test_once_exits_predictably_no_job(client: TestClient):
    class TCClient(GraphRecallClient):
        def lease(self, timeout_s: float = 25.0):
            return None

    w = GraphRecallWorker(TCClient("http://127.0.0.1:8090", "x", "w"))
    assert w.once() is None


def test_logs_do_not_contain_bearer(caplog):
    import logging
    from casual_board_graph_recall_worker.worker import _safe_log

    with caplog.at_level(logging.INFO):
        _safe_log("cook-1", "build", state="completed", token="SECRET", password="x")
    text = " ".join(r.message for r in caplog.records)
    assert "SECRET" not in text
    assert "password" not in text.lower() or "password=" not in text
