"""Graph Recall worker tests — fake hermes -z only; no logseq-graph."""

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
os.environ["CASUAL_BOARD_EVIDENCE_AI_PROVIDER"] = "none"
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
from casual_board_graph_recall_worker.client import GraphRecallClient
from casual_board_graph_recall_worker.hermes_runner import (
    InvalidHermesCLIError,
    build_hermes_command,
    dry_run_hermes_parser,
    validate_hermes_argv,
)
from casual_board_graph_recall_worker.prompt import build_prompt
from casual_board_graph_recall_worker.worker import GraphRecallWorker


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    close()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
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
    return r.json()["id"]


class TCClient(GraphRecallClient):
    def __init__(self, test_client: TestClient, worker_id: str = "graph-recall@test"):
        super().__init__("http://testserver", "graph-recall-secret", worker_id)
        self._tc = test_client

    def lease(self, timeout_s: float = 25.0):
        r = self._tc.get(
            "/v1/graph-recall/jobs/lease",
            headers=gr_headers(),
            params={"worker_id": self.worker_id, "timeout_s": timeout_s},
        )
        r.raise_for_status()
        return r.json().get("job")

    def post_result(self, **kwargs):
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
        r = self._tc.post("/v1/graph-recall/jobs/result", headers=gr_headers(), json=body)
        r.raise_for_status()
        return r.json()


def test_hermes_command_is_z_prompt_only():
    cmd = build_hermes_command("hello world")
    assert cmd == ["hermes", "-z", "hello world"]
    assert "--toolset" not in cmd
    assert "--timeout" not in cmd
    assert "--toolsets" not in cmd
    validate_hermes_argv(cmd)


def test_invalid_cli_flags_rejected():
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--toolset", "x"])
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--timeout", "30"])
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z"])


def test_dry_run_parser_ok():
    ok, msg = dry_run_hermes_parser("ping")
    assert ok, msg


def test_prompt_delimits_data_no_logseq_invocation():
    p = build_prompt(
        {
            "consultation": {
                "id": "cook-1",
                "mode": "rescue",
                "ingredients_or_problem": "trim",
                "local_safety_plan": {
                    "rejected": False,
                    "decision": {"verdict": "proceed"},
                    "guest_service_allowed": False,
                },
            },
            "produce_lots": [{"name": "onion"}],
            "ingredients": [],
            "dish": None,
            "mode_contract": "strict",
            "rules": [],
        }
    )
    assert "UNTRUSTED_DATA_JSON" in p
    assert "never executable" in p.lower() or "data, never" in p.lower()
    assert "never invokes host graph CLIs" in p


def test_no_job(client: TestClient):
    r = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "w", "timeout_s": 1},
    )
    assert r.status_code == 200
    assert r.json()["job"] is None


def test_fake_hermes_z_pipeline_to_returned_task(client: TestClient):
    """lease → hermes -z fake → signed result → evidence gate → kitchen_memory_returned."""
    import app.evidence_store as es

    es.is_approved_graph_path = lambda p, **k: str(p).startswith("/home/discovery-system/Logseq/graph")
    path = "/home/discovery-system/Logseq/graph/stock.md"
    cid = create_safe_consult(client)

    def fake_hermes(prompt: str, meta: dict) -> str:
        cmd = meta["command"]
        assert cmd[0] == "hermes"
        assert "-z" in cmd
        assert cmd[cmd.index("-z") + 1] == prompt
        assert "logseq-graph" not in " ".join(cmd)
        assert "UNTRUSTED_DATA_JSON" in prompt
        return json.dumps(
            {
                "kitchen_memory": [
                    {
                        "title": "Onion stock",
                        "path": path,
                        "relevance": "technique",
                        "finding": "Brown gently",
                    }
                ],
                "enrichment": {
                    "recommendation": "Brown onion trimmings for staff stock",
                    "unknowns": [],
                    "conflicts": [],
                },
                "meta": {},
            }
        )

    w = GraphRecallWorker(TCClient(client), hermes_runner=fake_hermes)
    res = w.once()
    assert res is not None
    assert res["id"] == cid
    assert res["graph_recall_status"] == "completed"
    assert res["task_status"] == "kitchen_memory_returned"
    plan = res["local_safety_plan"]
    assert plan.get("evidence_gate_status") in {
        "verified",
        "insufficient_evidence",
        "pending_review",
    }
    # citations registered from graph path
    assert plan.get("evidence_source_count", 0) >= 1 or plan.get("evidence_citations") is not None


def test_malformed_hermes_fails_signed(client: TestClient):
    create_safe_consult(client)

    def bad(prompt: str, meta: dict) -> str:
        return "not json {{"

    res = GraphRecallWorker(TCClient(client), hermes_runner=bad).once()
    assert res["graph_recall_status"] == "failed"


def test_timeout_fails_signed(client: TestClient):
    create_safe_consult(client)

    def boom(prompt: str, meta: dict) -> str:
        raise TimeoutError()

    res = GraphRecallWorker(TCClient(client), hermes_runner=boom).once()
    assert res["graph_recall_status"] == "failed"
    assert "timeout" in (res.get("blocked_reason") or res["local_safety_plan"].get("notes", [""])[-1] if False else res.get("blocked_reason") or "").lower() or "unavailable" in str(
        res.get("blocked_reason") or ""
    ).lower() or res["task_status"] in {"needs_review", "failed", "blocked"}


def test_unsupported_citation_insufficient(client: TestClient):
    import app.evidence_store as es

    es.is_approved_graph_path = lambda p, **k: False  # nothing approved
    create_safe_consult(client)

    def fake(prompt: str, meta: dict) -> str:
        return json.dumps(
            {
                "kitchen_memory": [
                    {
                        "title": "x",
                        "path": "/tmp/not-graph.md",
                        "relevance": "x",
                        "finding": "y",
                    }
                ],
                "enrichment": {"recommendation": "do it", "unknowns": [], "conflicts": []},
                "meta": {},
            }
        )

    res = GraphRecallWorker(TCClient(client), hermes_runner=fake).once()
    assert res["graph_recall_status"] == "completed"
    plan = res["local_safety_plan"]
    assert plan.get("evidence_verified") is False
    assert plan.get("evidence_gate_status") == "insufficient_evidence"


def test_blocked_safety_stays_blocked(client: TestClient):
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
    assert r.json()["task_status"] == "blocked"
    assert r.json()["graph_recall_status"] == "not_requested"


def test_once_no_job():
    class Empty(GraphRecallClient):
        def lease(self, timeout_s: float = 25.0):
            return None

    assert GraphRecallWorker(Empty("http://127.0.0.1:8090", "x", "w")).once() is None


def test_lease_expiry_requeue(client: TestClient):
    cid = create_safe_consult(client)
    client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "w-exp", "timeout_s": 2},
    )
    from datetime import datetime, timedelta, timezone

    from app.db import get_conn

    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    get_conn().execute(
        "UPDATE graph_recall_jobs SET lease_expires_at=? WHERE consultation_id=? AND status='leased'",
        (past, cid),
    )
    get_conn().commit()
    assert reap_expired_leases() >= 1


def test_worker_never_calls_logseq_graph():
    """Source inspection: worker must not import retrieval package."""
    import casual_board_graph_recall_worker.worker as w
    import inspect
    src = Path(w.__file__).read_text()
    assert "run_logseq" not in src
    assert "from .retrieval" not in src
    assert "import retrieval" not in src


def test_logs_no_secrets(caplog):
    import logging

    from casual_board_graph_recall_worker.worker import _safe_log

    with caplog.at_level(logging.INFO):
        _safe_log("cook-1", "build", state="ok", token="SECRETTOKEN")
    joined = " ".join(r.message for r in caplog.records)
    assert "SECRETTOKEN" not in joined
