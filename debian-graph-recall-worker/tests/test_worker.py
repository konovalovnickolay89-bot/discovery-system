"""Graph Recall worker tests — fake Hermes + fake logseq-graph only."""

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
from casual_board_graph_recall_worker.client import GraphRecallClient
from casual_board_graph_recall_worker.hermes_runner import (
    InvalidHermesCLIError,
    build_hermes_command,
    dry_run_hermes_parser,
    validate_hermes_argv,
)
from casual_board_graph_recall_worker.prompt import build_prompt
from casual_board_graph_recall_worker.retrieval import (
    build_logseq_recall_command,
    build_recall_query,
    sanitise_query_fragment,
)
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


def test_hermes_command_uses_toolsets_not_toolset_and_prompt_after_z():
    cmd = build_hermes_command("hello world", toolsets="")
    assert cmd[0] == "hermes"
    assert "-z" in cmd
    zi = cmd.index("-z")
    assert cmd[zi + 1] == "hello world"
    assert "--toolset" not in cmd
    assert "--timeout" not in cmd
    # synthesis-only default: no --toolsets means no terminal/file tools
    assert "--toolsets" not in cmd
    validate_hermes_argv(cmd)

    cmd2 = build_hermes_command("p", toolsets="memory")
    assert "--toolsets" in cmd2
    assert cmd2[cmd2.index("--toolsets") + 1] == "memory"
    assert "--toolset" not in cmd2
    assert "--timeout" not in cmd2


def test_invalid_cli_flags_rejected_before_install():
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--toolset", "x"])
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--timeout", "30"])
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z"])  # missing prompt
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--toolsets", "terminal"])
    with pytest.raises(InvalidHermesCLIError):
        validate_hermes_argv(["hermes", "-z", "x", "--toolsets", "file"])


def test_dry_run_parser_ok_without_binary():
    ok, msg = dry_run_hermes_parser("ping")
    assert ok, msg
    assert "toolset" not in msg.lower() or "without --toolset" in msg


def test_logseq_recall_command_shell_false_bounded():
    cmd = build_logseq_recall_command("onion soup; rm -rf /", limit=6)
    assert cmd[0] == "logseq-graph"
    assert cmd[1] == "recall"
    assert cmd[3] == "--limit"
    assert cmd[4] == "6"
    assert ";" not in cmd[2]
    assert not cmd[2].startswith("-")
    assert len(cmd) == 5
    # ensure no shell metacharacters in query arg
    for bad in (";", "|", "&", "`", "$", "\n"):
        assert bad not in cmd[2]


def test_query_sanitises_user_text():
    q = sanitise_query_fragment("$(reboot) && cat /etc/passwd; --force", max_len=80)
    assert "$" not in q
    assert ";" not in q
    assert not q.startswith("-")
    payload = {
        "consultation": {
            "mode": "build",
            "title": "soup",
            "ingredients_or_problem": "onion\n`rm -rf`",
            "desired_outcome": "staff meal",
        },
        "produce_lots": [],
        "ingredients": [],
    }
    query = build_recall_query(payload)
    assert "rm" in query or "onion" in query
    assert "`" not in query
    assert len(query) <= 160


def test_prompt_includes_retrieved_and_safety():
    p = build_prompt(
        {
            "consultation": {
                "id": "cook-1",
                "mode": "rescue",
                "local_safety_plan": {
                    "rejected": True,
                    "decision": {"verdict": "discard_or_escalate"},
                },
            },
            "mode_contract": "strict",
            "rules": [],
        },
        retrieved_context=[{"title": "x", "path": "/home/discovery-system/Logseq/graph/a.md"}],
    )
    assert "RETRIEVED_NOTES_JSON" in p
    assert "discard_or_escalate" in p
    assert "NO shell" in p or "no shell" in p.lower()


def test_no_job(client: TestClient):
    r = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr_headers(),
        params={"worker_id": "w", "timeout_s": 1},
    )
    assert r.status_code == 200
    assert r.json()["job"] is None


def test_once_completed_with_fake_recall_and_hermes(client: TestClient, tmp_path: Path):
    create_safe_consult(client)
    graph = tmp_path / "graph"
    graph.mkdir()
    note = graph / "onion.md"
    note.write_text("stock")

    def fake_recall(cmd: list[str]) -> str:
        assert cmd[0] == "logseq-graph"
        assert cmd[1] == "recall"
        assert "--limit" in cmd
        assert len(cmd) == 5
        return f"{note}\tOnion stock\tBrown gently"

    def fake_hermes(prompt: str, meta: dict) -> str:
        cmd = meta["command"]
        assert "-z" in cmd
        assert cmd[cmd.index("-z") + 1] == prompt
        assert "--toolset" not in cmd
        assert "--timeout" not in cmd
        # synthesis-only
        assert "--toolsets" not in cmd or "terminal" not in " ".join(cmd)
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
                        "title": "bad",
                        "path": "/etc/passwd",
                        "relevance": "x",
                        "finding": "no",
                    },
                ],
                "enrichment": {"note": "simple"},
            }
        )

    import casual_board_graph_recall_worker.hermes_runner as hr

    old = hr.LOGSEQ_GRAPH_ROOT
    hr.LOGSEQ_GRAPH_ROOT = str(graph)
    try:
        w = GraphRecallWorker(
            TCClient(client),
            hermes_runner=fake_hermes,
            recall_runner=fake_recall,
            hermes_toolsets="",
            graph_root=str(graph),
        )
        res = w.once()
        assert res["graph_recall_status"] == "completed"
        mem = res["local_safety_plan"]["kitchen_memory"]
        assert any(m["title"] == "Onion stock" for m in mem)
        assert not any("/etc/passwd" in (m.get("path") or "") for m in mem)
    finally:
        hr.LOGSEQ_GRAPH_ROOT = old


def test_malformed_hermes_fails_signed(client: TestClient, tmp_path: Path):
    create_safe_consult(client)

    def fake_recall(cmd: list[str]) -> str:
        return ""

    def bad(prompt: str, meta: dict) -> str:
        return "not json"

    w = GraphRecallWorker(
        TCClient(client),
        hermes_runner=bad,
        recall_runner=fake_recall,
        graph_root=str(tmp_path),
    )
    res = w.once()
    assert res["graph_recall_status"] == "failed"


def test_wrong_auth_and_replay(client: TestClient):
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
    h = session(client)
    c = client.get(f"/v1/cook/consultations/{cid}", headers=h).json()
    assert c["graph_recall_status"] == "queued"
    assert c["task_status"] == "kitchen_memory_queued"


def test_blocked_safety_not_queued(client: TestClient):
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
    assert r.json()["graph_recall_status"] == "not_requested"
    assert r.json()["local_safety_plan"]["rejected"] is True


def test_once_no_job_exits():
    class Empty(GraphRecallClient):
        def lease(self, timeout_s: float = 25.0):
            return None

    assert GraphRecallWorker(Empty("http://127.0.0.1:8090", "x", "w")).once() is None


def test_deploy_doc_no_git_pull_in_opt():
    doc = Path(__file__).resolve().parents[2] / "deploy/self-host/GRAPH_RECALL_WORKER.md"
    text = doc.read_text()
    assert "git pull" not in text or "Do not run `git pull` inside `/opt/casual-board`" in text
    # no instructional pull inside opt
    assert "cd /opt/casual-board && git pull" not in text
    assert "rsync" in text
    assert "mktemp" in text or "STAGE" in text


def test_logs_no_secrets(caplog):
    import logging

    from casual_board_graph_recall_worker.worker import _safe_log

    with caplog.at_level(logging.INFO):
        _safe_log("cook-1", "build", state="ok", token="SECRETTOKEN")
    joined = " ".join(r.message for r in caplog.records)
    assert "SECRETTOKEN" not in joined
