"""Cook Studio: kitchen CRUD, consultations, Graph Recall queue boundaries."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/cook-studio-test"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret-distinct"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret-distinct"
os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
os.environ["CASUAL_BOARD_UI_PASSWORD"] = "ui-pass-secret"
os.environ["CASUAL_BOARD_SESSION_SECRET"] = "session-hmac-secret"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ["CASUAL_BOARD_CORS_ORIGINS"] = "https://discovery-system.grok.me"
os.environ["CASUAL_BOARD_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"

from app.config import get_settings
from app.db import close
from app.graph_recall_queue import sign_result
from app.main import app
from app.store import reset_store_for_tests


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


def gr():
    return {"Authorization": "Bearer graph-recall-secret"}


def test_kitchen_crud_session_protected(client: TestClient):
    assert client.get("/v1/kitchen/produce").status_code == 401
    assert client.get("/v1/kitchen/ingredients").status_code == 401
    assert client.get("/v1/kitchen/dishes").status_code == 401
    h = session(client)
    p = client.post(
        "/v1/kitchen/produce",
        headers=h,
        json={"name": "onion ends", "quantity": 2, "unit": "kg", "storage_location": "fridge"},
    )
    assert p.status_code == 200
    lot_id = p.json()["id"]
    i = client.post("/v1/kitchen/ingredients", headers=h, json={"name": "onion", "category": "veg"})
    assert i.status_code == 200
    ing_id = i.json()["id"]
    d = client.post(
        "/v1/kitchen/dishes",
        headers=h,
        json={
            "name": "staff soup",
            "type": "dish",
            "links": [{"ingredient_id": ing_id, "name": "onion", "quantity": 1, "unit": "kg"}],
        },
    )
    assert d.status_code == 200
    assert client.get("/v1/kitchen/produce", headers=h).json()[0]["id"] == lot_id
    assert client.get("/v1/kitchen/ingredients", headers=h).json()[0]["id"] == ing_id
    assert client.get("/v1/kitchen/dishes", headers=h).json()[0]["name"] == "staff soup"


def test_consultation_auth_and_persist(client: TestClient):
    assert client.post(
        "/v1/cook/consultations",
        json={"mode": "build", "ingredients_or_problem": "carrot"},
    ).status_code == 401
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "build",
            "ingredients_or_problem": "carrot, onion, herb",
            "traceability": "labelled_chilled_known",
            "service_context": "staff_meal",
            "allergens": ["celery"],
            "desired_outcome": "soup",
            "request_graph_recall": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"].startswith("cook-")
    assert body["task_status"] in {"kitchen_memory_queued", "local_plan_ready"}
    assert body["local_safety_plan"]["decision"]["verdict"] in {"proceed", "caution"}
    g = client.get(f"/v1/cook/consultations/{body['id']}", headers=h)
    assert g.status_code == 200
    assert g.json()["id"] == body["id"]


def test_rescue_guest_exposed_blocked_no_creative(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "rescue",
            "ingredients_or_problem": "buffet roast",
            "traceability": "guest_exposed_buffet",
            "service_context": "a_la_carte",
            "request_graph_recall": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_status"] == "blocked"
    assert body["graph_recall_status"] == "not_requested"
    plan = body["local_safety_plan"]
    assert plan["rejected"] is True
    assert plan["disposal_checklist"]
    assert plan["decision"]["verdict"] == "discard_or_escalate"


def test_modes_build_service_develop(client: TestClient):
    h = session(client)
    for mode in ("build", "service", "develop"):
        r = client.post(
            "/v1/cook/consultations",
            headers=h,
            json={
                "mode": mode,
                "ingredients_or_problem": "potato, leek",
                "traceability": "labelled_chilled_known",
                "service_context": "canteen",
                "request_graph_recall": False,
            },
        )
        assert r.status_code == 200, mode
        plan = r.json()["local_safety_plan"]
        assert plan["rejected"] is False
        assert plan["primary_plan"]
        assert plan["recipe_spine"]["purpose"]


def test_graph_recall_lease_hmac_and_no_safety_override(client: TestClient):
    h = session(client)
    blocked = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "rescue",
            "ingredients_or_problem": "chicken, rice",
            "traceability": "unknown",
            "service_context": "banqueting",
            "request_graph_recall": True,
        },
    ).json()
    assert blocked["graph_recall_status"] == "not_requested"

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
    cid = r.json()["id"]
    assert r.json()["graph_recall_status"] == "queued"
    assert r.json()["local_safety_plan"]["guest_service_allowed"] is not None

    assert client.get("/v1/graph-recall/jobs/lease?timeout_s=1").status_code == 401
    assert (
        client.get(
            "/v1/graph-recall/jobs/lease?timeout_s=1",
            headers={"Authorization": "Bearer bridge-secret-distinct"},
        ).status_code
        == 403
    )

    lease = client.get(
        "/v1/graph-recall/jobs/lease",
        headers=gr(),
        params={"worker_id": "gr-1", "timeout_s": 2},
    )
    assert lease.status_code == 200
    job = lease.json()["job"]
    assert job is not None
    assert job["consultation_id"] == cid
    nonce = job["lease_nonce"]

    mem = [
        {
            "title": "Onion stock notes",
            "path": "logseq/kitchen/onion",
            "relevance": "stock",
            "excerpt": "…",
        }
    ]
    enrichment = {"primary_plan": {"summary": "Use brown stock base"}}
    sig = sign_result(
        consultation_id=cid,
        status="completed",
        worker_id="gr-1",
        lease_nonce=nonce,
        kitchen_memory=mem,
        enrichment=enrichment,
        message="ok",
    )
    done = client.post(
        "/v1/graph-recall/jobs/result",
        headers=gr(),
        json={
            "consultation_id": cid,
            "status": "completed",
            "kitchen_memory": mem,
            "enrichment": enrichment,
            "message": "ok",
            "worker_id": "gr-1",
            "lease_nonce": nonce,
            "signature": sig,
            "proposed_guest_service": True,
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    plan = body["local_safety_plan"]
    assert any(m["title"] == "Onion stock notes" for m in plan["kitchen_memory"])
    if not plan.get("guest_service_allowed"):
        notes = " ".join(plan.get("notes") or []).lower()
        assert "local safety" in notes or "guest service" in notes

    replay = client.post(
        "/v1/graph-recall/jobs/result",
        headers=gr(),
        json={
            "consultation_id": cid,
            "status": "completed",
            "kitchen_memory": mem,
            "enrichment": enrichment,
            "message": "ok",
            "worker_id": "gr-1",
            "lease_nonce": nonce,
            "signature": sig,
        },
    )
    assert replay.status_code in (409, 403)


def test_local_plan_without_worker(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "develop",
            "ingredients_or_problem": "roast chicken",
            "traceability": "labelled_chilled_known",
            "service_context": "a_la_carte",
            "request_graph_recall": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["graph_recall_status"] == "not_requested"
    assert r.json()["task_status"] == "local_plan_ready"
    assert r.json()["local_safety_plan"]["alternatives"]
