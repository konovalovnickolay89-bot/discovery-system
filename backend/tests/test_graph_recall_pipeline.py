"""End-to-end Graph Recall pipeline: fake hermes → lease/result → reviewer → gate."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/gr-pipeline-test"
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "debian-graph-recall-worker"))

from app.config import get_settings
from app.db import close
from app.evidence_models import EvidenceGateStatus
from app.evidence_reviewer import EvidenceReviewerUnavailable
from app.graph_recall_queue import sign_result
from app.main import app
from app.store import reset_store_for_tests
from casual_board_graph_recall_worker.client import GraphRecallClient, sign_result as client_sign
from casual_board_graph_recall_worker.worker import GraphRecallWorker


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    close()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    os.environ["CASUAL_BOARD_EVIDENCE_AI_PROVIDER"] = "none"
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def session(client: TestClient) -> dict:
    r = client.post("/v1/auth/login", json={"password": "ui-pass-secret"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def gr_h():
    return {"Authorization": "Bearer graph-recall-secret"}


class Bridge(GraphRecallClient):
    def __init__(self, tc: TestClient):
        super().__init__("http://testserver", "graph-recall-secret", "graph-recall@debian-minimal")
        self.tc = tc

    def lease(self, timeout_s: float = 25.0):
        return (
            self.tc.get(
                "/v1/graph-recall/jobs/lease",
                headers=gr_h(),
                params={"worker_id": self.worker_id, "timeout_s": timeout_s},
            )
            .json()
            .get("job")
        )

    def post_result(self, **kwargs):
        body = {
            "consultation_id": kwargs["consultation_id"],
            "status": kwargs["status"],
            "kitchen_memory": kwargs.get("kitchen_memory") or [],
            "enrichment": kwargs.get("enrichment") or {},
            "message": kwargs.get("message") or "",
            "worker_id": self.worker_id,
            "lease_nonce": kwargs["lease_nonce"],
            "signature": client_sign(
                self.token,
                consultation_id=kwargs["consultation_id"],
                status=kwargs["status"],
                worker_id=self.worker_id,
                lease_nonce=kwargs["lease_nonce"],
                kitchen_memory=kwargs.get("kitchen_memory") or [],
                enrichment=kwargs.get("enrichment") or {},
                message=kwargs.get("message") or "",
            ),
        }
        r = self.tc.post("/v1/graph-recall/jobs/result", headers=gr_h(), json=body)
        r.raise_for_status()
        return r.json()


def test_full_pipeline_fake_hermes_to_task(client: TestClient):
    import app.evidence_store as es

    es.is_approved_graph_path = lambda p, **k: str(p).startswith("/home/discovery-system/Logseq/graph")
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "build",
            "ingredients_or_problem": "onion trimmings",
            "traceability": "labelled_chilled_known",
            "service_context": "staff_meal",
            "request_graph_recall": True,
        },
    )
    assert r.json()["graph_recall_status"] == "queued"
    cid = r.json()["id"]

    def hermes(prompt: str, meta: dict) -> str:
        assert meta["command"] == ["hermes", "-z", prompt]
        return json.dumps(
            {
                "kitchen_memory": [
                    {
                        "title": "Stock card",
                        "path": "/home/discovery-system/Logseq/graph/stock.md",
                        "relevance": "stock",
                        "finding": "Brown onions",
                    }
                ],
                "enrichment": {
                    "recommendation": "Make brown stock for staff soup",
                    "unknowns": [],
                    "conflicts": [],
                },
                "meta": {},
            }
        )

    out = GraphRecallWorker(Bridge(client), hermes_runner=hermes).once()
    assert out["id"] == cid
    assert out["task_status"] == "kitchen_memory_returned"
    assert out["graph_recall_status"] == "completed"
    plan = out["local_safety_plan"]
    assert plan["evidence_gate_status"] == EvidenceGateStatus.verified.value
    assert plan["evidence_verified"] is True
    assert plan["evidence_source_count"] >= 1

    # WS-facing state visible via get
    g = client.get(f"/v1/cook/consultations/{cid}", headers=h).json()
    assert g["task_status"] == "kitchen_memory_returned"
    assert g["local_safety_plan"]["evidence_citations"]


def test_reviewer_unavailable_insufficient(client: TestClient, monkeypatch):
    import app.evidence_store as es
    import app.evidence_gate as eg

    es.is_approved_graph_path = lambda p, **k: str(p).startswith("/home/discovery-system/Logseq/graph")
    os.environ["CASUAL_BOARD_EVIDENCE_AI_PROVIDER"] = "openai"
    get_settings.cache_clear()

    def boom(*a, **k):
        raise EvidenceReviewerUnavailable("simulated")

    monkeypatch.setattr("app.evidence_reviewer.review_graph_recall_output", boom)
    # also patch through gate's import path
    monkeypatch.setattr(
        "app.evidence_gate.structure_with_pydantic_ai",
        lambda **kw: (_ for _ in ()).throw(EvidenceReviewerUnavailable("simulated")),
    )

    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "build",
            "ingredients_or_problem": "onion",
            "traceability": "labelled_chilled_known",
            "service_context": "staff_meal",
            "request_graph_recall": True,
        },
    )
    cid = r.json()["id"]

    def hermes(prompt: str, meta: dict) -> str:
        return json.dumps(
            {
                "kitchen_memory": [
                    {
                        "title": "S",
                        "path": "/home/discovery-system/Logseq/graph/s.md",
                        "relevance": "x",
                        "finding": "y",
                    }
                ],
                "enrichment": {"recommendation": "ok", "unknowns": [], "conflicts": []},
                "meta": {},
            }
        )

    # Patch apply path - structure raises inside apply
    from app.evidence_reviewer import EvidenceReviewerUnavailable as ERU

    def failing_structure(**kwargs):
        raise ERU("down")

    monkeypatch.setattr(eg, "structure_with_pydantic_ai", failing_structure)

    out = GraphRecallWorker(Bridge(client), hermes_runner=hermes).once()
    assert out["graph_recall_status"] == "completed"
    plan = out["local_safety_plan"]
    assert plan["evidence_gate_status"] == "insufficient_evidence"
    assert plan["evidence_verified"] is False
    os.environ["CASUAL_BOARD_EVIDENCE_AI_PROVIDER"] = "none"
    get_settings.cache_clear()
