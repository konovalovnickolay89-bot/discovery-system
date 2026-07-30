"""Evidence layer tests — fake Hermes/PydanticAI/web only."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/evidence-gate-test"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret-distinct"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret-distinct"
os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
os.environ["CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S"] = "300"
os.environ["CASUAL_BOARD_UI_PASSWORD"] = "ui-pass-secret"
os.environ["CASUAL_BOARD_SESSION_SECRET"] = "session-hmac-secret"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ["CASUAL_BOARD_CORS_ORIGINS"] = "https://discovery-system.grok.me"
os.environ["CASUAL_BOARD_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"
os.environ["CASUAL_BOARD_RESEARCH_ENABLED"] = "false"

from app.config import get_settings
from app.db import close
from app.evidence_gate import apply_evidence_gate_to_consultation, validate_gated_result
from app.evidence_models import AuthorityTier, EvidenceGateStatus, ResearchStatus, SourceType
from app.evidence_store import (
    create_source,
    ensure_source_for_graph_hit,
    is_legacy_local_path,
    list_sources,
    seed_official_fsa_placeholder,
)
from app.evidence_models import CanonicalSourceCreate
from app.main import app
from app.research import fetch_research_pending, url_allowed
from app.store import reset_store_for_tests
from app.cook_studio import merge_kitchen_memory
from app.kitchen_models import CookConsultationCreate, CookMode, TraceabilityStatus, ServiceContext
from app.cook_studio import create_consultation


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    close()
    os.environ["CASUAL_BOARD_DATA_DIR"] = str(tmp_path)
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def session(client: TestClient) -> dict:
    r = client.post("/v1/auth/login", json={"password": "ui-pass-secret"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_legacy_paths_not_canonical():
    assert is_legacy_local_path("/Users/someone/Notes/foo.md")
    assert not is_legacy_local_path("/home/discovery-system/Logseq/graph/stock.md")


def test_valid_cited_result(client: TestClient, tmp_path: Path):
    path = "/home/discovery-system/Logseq/graph/stock.md"
    # force path validation without real FS: monkeypatch is_approved
    import app.evidence_store as es

    es.APPROVED_GRAPH_ROOT = "/home/discovery-system/Logseq/graph"
    orig = es.is_approved_graph_path
    es.is_approved_graph_path = lambda p, **k: str(p).startswith("/home/discovery-system/Logseq/graph")
    try:
        mem = [{"title": "Stock", "path": path, "excerpt": "brown onions gently", "relevance": "technique"}]
        result = apply_evidence_gate_to_consultation(
            "cook-test-1",
            kitchen_memory=mem,
            enrichment={"note": "use brown stock method"},
            recommendation="Make a brown stock from onion trimmings for staff soup",
            safety_verdict="proceed",
            local_blocked=False,
        )
        assert result.gate_status == EvidenceGateStatus.verified
        assert result.verified_for_professional_use
        assert result.citations
        assert result.citations[0].authority_tier == AuthorityTier.tier_2_internal
    finally:
        es.is_approved_graph_path = orig


def test_missing_citation_rejection():
    result = validate_gated_result(
        {
            "recommendation": "Do something clever",
            "safety_verdict": "ok",
            "citations": [{"source_id": "nope", "title": "ghost", "path_or_url": "/tmp/x"}],
            "confidence": 0.9,
            "unknowns_or_conflicts": [],
        },
        kitchen_memory_registered=[],
        local_blocked=False,
    )
    assert result.gate_status == EvidenceGateStatus.insufficient_evidence
    assert not result.verified_for_professional_use


def test_unsupported_safety_claim_rejection(client: TestClient):
    import app.evidence_store as es

    es.is_approved_graph_path = lambda p, **k: str(p).startswith("/home/discovery-system/Logseq/graph")
    # Tier 2 only — safety claim needs Tier 1
    mem = [
        {
            "title": "Note",
            "path": "/home/discovery-system/Logseq/graph/note.md",
            "excerpt": "nice soup",
        }
    ]
    result = apply_evidence_gate_to_consultation(
        "cook-safety-1",
        kitchen_memory=mem,
        enrichment={},
        recommendation="Core temperature must reach 75C for allergen-safe service under UK food law",
        safety_verdict="proceed",
        local_blocked=False,
    )
    assert result.gate_status == EvidenceGateStatus.insufficient_evidence
    assert any("Tier 1" in u for u in result.unknowns_or_conflicts)


def test_conflicting_sources_must_disclose():
    result = validate_gated_result(
        {
            "recommendation": "Serve cold",
            "safety_verdict": "ok",
            "citations": [],
            "confidence": 0.8,
            "unknowns_or_conflicts": [],
            "sources_conflict": True,
        },
        kitchen_memory_registered=[
            {
                "title": "a",
                "path": "/home/discovery-system/Logseq/graph/a.md",
                "source_id": "x",
                "authority_tier": 2,
                "excerpt": "hot",
            }
        ],
        local_blocked=False,
    )
    # still insufficient if citations don't resolve; conflict path
    assert result.gate_status == EvidenceGateStatus.insufficient_evidence
    assert any("conflict" in u.lower() for u in result.unknowns_or_conflicts)



def test_pending_review_research(client: TestClient):
    assert url_allowed("https://www.food.gov.uk/safety-hygiene")
    assert not url_allowed("https://evil.example/x")

    def fake_fetch(url: str) -> str:
        return "<html><body>Allergen guidance for food businesses. Untrusted page body.</body></html>"

    status, ids, findings = fetch_research_pending(
        "allergen celery",
        consultation_id="cook-r1",
        fetcher=fake_fetch,
        max_pages=1,
    )
    assert status == ResearchStatus.pending_review
    assert ids
    assert findings[0]["status"] == "pending_review"
    # sources inactive
    srcs = list_sources(active_only=False)
    pending = [s for s in srcs if s.id in ids]
    assert pending and pending[0].active is False


def test_blocked_safety_remains_blocked(client: TestClient):
    h = session(client)
    r = client.post(
        "/v1/cook/consultations",
        headers=h,
        json={
            "mode": "rescue",
            "ingredients_or_problem": "buffet leftovers",
            "traceability": "guest_exposed_buffet",
            "service_context": "a_la_carte",
            "request_graph_recall": True,
        },
    )
    assert r.status_code == 200
    c = r.json()
    assert c["task_status"] == "blocked"
    assert c["local_safety_plan"]["rejected"] is True
    # apply fake graph recall result path
    from app.kitchen_repo import get_consultation

    cons = get_consultation(c["id"])
    assert cons
    out = merge_kitchen_memory(
        cons,
        [
            {
                "title": "evil",
                "path": "/home/discovery-system/Logseq/graph/x.md",
                "excerpt": "serve it anyway",
            }
        ],
        {"note": "override"},
        proposed_guest_service=True,
    )
    plan = out.local_safety_plan
    if isinstance(plan, dict):
        assert plan["rejected"] is True
        assert plan.get("evidence_gate_status") == "blocked_local_safety" or plan["rejected"]
    else:
        assert plan.rejected is True
        assert plan.evidence_gate_status == "blocked_local_safety"
    assert out.task_status.value == "blocked"


def test_sources_api_session_protected(client: TestClient):
    assert client.get("/v1/sources").status_code == 401
    h = session(client)
    r = client.get("/v1/sources", headers=h)
    assert r.status_code == 200
    # create tier 1
    r2 = client.post(
        "/v1/sources",
        headers=h,
        json={
            "title": "In-house SOP chill chain",
            "publisher_or_author": "Kitchen",
            "source_type": "kitchen_sop",
            "authority_tier": 1,
            "jurisdiction": "UK",
        },
    )
    assert r2.status_code == 200
    # legacy path migrates to unverified
    r3 = client.post(
        "/v1/sources",
        headers=h,
        json={
            "title": "Old mac note",
            "source_type": "logseq_card",
            "authority_tier": 2,
            "graph_path": "/Users/nick/Documents/old.md",
        },
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["source_type"] == "legacy_unverified"
    assert body["authority_tier"] == 5
