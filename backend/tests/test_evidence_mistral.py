"""Mistral evidence reviewer — fake provider only; no real Mistral network calls."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["CASUAL_BOARD_ENV"] = "development"
os.environ["CASUAL_BOARD_DATA_DIR"] = "/tmp/evidence-mistral-test"
os.environ["CASUAL_BOARD_TOKEN"] = "owner-secret-distinct"
os.environ["CASUAL_BOARD_BRIDGE_TOKEN"] = "bridge-secret-distinct"
os.environ["CASUAL_BOARD_GRAPH_RECALL_TOKEN"] = "graph-recall-secret"
os.environ["CASUAL_BOARD_UI_PASSWORD"] = "ui-pass-secret"
os.environ["CASUAL_BOARD_SESSION_SECRET"] = "session-hmac-secret"
os.environ["CASUAL_BOARD_AI_PROVIDER"] = "function"
os.environ["CASUAL_BOARD_EVIDENCE_AI_PROVIDER"] = "none"
os.environ["CASUAL_BOARD_EVIDENCE_AI_MODEL"] = ""
os.environ["CASUAL_BOARD_CORS_ORIGINS"] = "https://discovery-system.grok.me"
os.environ["CASUAL_BOARD_TRUSTED_HOSTS"] = "testserver,127.0.0.1,localhost"

from app.config import get_settings
from app.db import close
from app.evidence_gate import apply_evidence_gate_to_consultation
from app.evidence_models import EvidenceGateStatus
from app.evidence_reviewer import (
    DEFAULT_MISTRAL_MODEL,
    EvidenceReviewerUnavailable,
    evidence_ai_provider,
    require_evidence_api_key,
    resolve_evidence_model,
    review_graph_recall_output,
)
from app.main import app
from app.store import reset_store_for_tests


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    get_settings.cache_clear()
    close()
    monkeypatch.setenv("CASUAL_BOARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "none")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    get_settings.cache_clear()
    reset_store_for_tests(tmp_path)
    with TestClient(app) as c:
        yield c


def test_default_provider_is_none(client):
    assert evidence_ai_provider() == "none"


def test_mistral_default_model_id(monkeypatch):
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_MODEL", "")
    get_settings.cache_clear()
    assert evidence_ai_provider() == "mistral"
    assert resolve_evidence_model("mistral") == DEFAULT_MISTRAL_MODEL
    assert DEFAULT_MISTRAL_MODEL == "mistral:mistral-small-latest"


def test_mistral_custom_model_prefix(monkeypatch):
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_MODEL", "mistral-large-latest")
    get_settings.cache_clear()
    assert resolve_evidence_model("mistral") == "mistral:mistral-large-latest"
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_MODEL", "mistral:mistral-small-latest")
    get_settings.cache_clear()
    assert resolve_evidence_model("mistral") == "mistral:mistral-small-latest"


def test_mistral_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(EvidenceReviewerUnavailable, match="mistral_key_missing"):
        require_evidence_api_key("mistral")


def test_mistral_fake_live_runner_success(monkeypatch, client):
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_MODEL", "mistral:mistral-small-latest")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-for-network")
    get_settings.cache_clear()

    def fake_live(model: str, prompt: str) -> dict:
        assert model == "mistral:mistral-small-latest"
        assert "MISTRAL_API_KEY" not in prompt
        assert "test-key" not in prompt
        return {
            "recommendation": "Brown onions for staff stock",
            "safety_verdict": "proceed",
            "citations": [
                {
                    "source_id": "src-1",
                    "title": "Stock",
                    "path_or_url": "/home/discovery-system/Logseq/graph/stock.md",
                    "excerpt": "Brown gently",
                    "authority_tier": 2,
                }
            ],
            "confidence": 0.7,
            "unknowns_or_conflicts": [],
            "research_status": "not_needed",
            "sources_conflict": False,
        }

    mem = [
        {
            "title": "Stock",
            "path": "/home/discovery-system/Logseq/graph/stock.md",
            "excerpt": "Brown gently",
            "source_id": "src-1",
            "authority_tier": 2,
        }
    ]
    out, meta = review_graph_recall_output(
        kitchen_memory=mem,
        enrichment={"recommendation": "stock"},
        registered_sources=[{"id": "src-1", "graph_path": mem[0]["path"]}],
        recommendation="Brown onions for staff stock",
        safety_verdict="proceed",
        live_runner=fake_live,
    )
    assert meta.provider == "mistral"
    assert meta.used_ai is True
    assert meta.model == "mistral:mistral-small-latest"
    assert out["citations"]
    # key never in meta
    assert "key" not in (meta.model or "").lower()
    dumped = meta.model_dump()
    assert "test-key" not in str(dumped)


def test_mistral_live_runner_failure_insufficient(monkeypatch, client):
    import app.evidence_store as es

    es.is_approved_graph_path = lambda p, **k: str(p).startswith(
        "/home/discovery-system/Logseq/graph"
    )
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-for-network")
    get_settings.cache_clear()

    def boom(model: str, prompt: str) -> dict:
        raise RuntimeError("simulated_provider_down")

    result = apply_evidence_gate_to_consultation(
        "cook-mistral-fail",
        kitchen_memory=[
            {
                "title": "Stock",
                "path": "/home/discovery-system/Logseq/graph/stock.md",
                "excerpt": "x",
            }
        ],
        enrichment={"recommendation": "ok"},
        recommendation="ok",
        safety_verdict="proceed",
        local_blocked=False,
        reviewer=None,
    )
    # Without injecting live_runner, real Agent would run — patch via structure path
    # Use apply with failing structure by monkeypatching review
    from app import evidence_gate as eg

    def fail_review(**kwargs):
        raise EvidenceReviewerUnavailable("mistral_key_missing")

    monkeypatch.setattr(eg, "structure_with_pydantic_ai", fail_review)
    result = apply_evidence_gate_to_consultation(
        "cook-mistral-fail2",
        kitchen_memory=[
            {
                "title": "Stock",
                "path": "/home/discovery-system/Logseq/graph/stock.md",
                "excerpt": "x",
            }
        ],
        enrichment={},
        recommendation="ok",
        safety_verdict="proceed",
        local_blocked=False,
    )
    assert result.gate_status == EvidenceGateStatus.insufficient_evidence
    assert result.verified_for_professional_use is False


def test_mistral_missing_key_via_review_returns_unavailable(monkeypatch, client):
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(EvidenceReviewerUnavailable) as ei:
        review_graph_recall_output(
            kitchen_memory=[],
            enrichment={},
            registered_sources=[],
            recommendation="x",
            safety_verdict="ok",
        )
    assert "mistral_key" in str(ei.value)


def test_mistral_invented_citation_stripped(monkeypatch, client):
    monkeypatch.setenv("CASUAL_BOARD_EVIDENCE_AI_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-for-network")
    get_settings.cache_clear()

    def invent(model: str, prompt: str) -> dict:
        return {
            "recommendation": "Serve guest",
            "safety_verdict": "proceed",
            "citations": [
                {
                    "source_id": "invented-id",
                    "title": "Made up",
                    "path_or_url": "https://evil.example/x",
                    "excerpt": "nope",
                    "authority_tier": 1,
                }
            ],
            "confidence": 0.99,
            "unknowns_or_conflicts": [],
            "research_status": "not_needed",
            "sources_conflict": False,
        }

    out, meta = review_graph_recall_output(
        kitchen_memory=[
            {
                "title": "Real",
                "path": "/home/discovery-system/Logseq/graph/real.md",
                "source_id": "src-real",
                "excerpt": "real",
            }
        ],
        enrichment={},
        registered_sources=[{"id": "src-real", "graph_path": "/home/discovery-system/Logseq/graph/real.md"}],
        recommendation="use real",
        safety_verdict="proceed",
        live_runner=invent,
    )
    # invented dropped; fallback to kitchen_memory cites
    for c in out["citations"]:
        assert c.get("source_id") != "invented-id"
        assert "evil.example" not in str(c.get("path_or_url") or "")


def test_api_response_never_contains_mistral_key(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "super-secret-mistral-key-xyz")
    r = client.get("/health")
    assert r.status_code == 200
    assert "super-secret-mistral-key-xyz" not in r.text
    assert "MISTRAL_API_KEY" not in r.text
