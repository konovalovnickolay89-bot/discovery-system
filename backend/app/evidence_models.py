"""Canonical sources + evidence gate models. Pydantic validates structure; not truth itself."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AuthorityTier(int, Enum):
    """1 = highest (official) … 5 = non-authoritative inspiration."""

    tier_1_official = 1
    tier_2_internal = 2
    tier_3_classical = 3
    tier_4_research = 4
    tier_5_inspiration = 5


class SourceType(str, Enum):
    official_authority = "official_authority"
    supplier_spec = "supplier_spec"
    kitchen_sop = "kitchen_sop"
    internal_recipe = "internal_recipe"
    classical_reference = "classical_reference"
    peer_reviewed = "peer_reviewed"
    technical_article = "technical_article"
    logseq_card = "logseq_card"
    research_fetch = "research_fetch"
    legacy_unverified = "legacy_unverified"
    inspiration = "inspiration"


class ResearchStatus(str, Enum):
    not_needed = "not_needed"
    pending_review = "pending_review"
    unavailable = "unavailable"


class EvidenceGateStatus(str, Enum):
    verified = "verified"
    insufficient_evidence = "insufficient_evidence"
    blocked_local_safety = "blocked_local_safety"
    pending_review = "pending_review"


class CanonicalSource(BaseModel):
    id: str = Field(default_factory=lambda: f"src-{uuid4().hex[:12]}")
    title: str
    publisher_or_author: str = ""
    source_type: SourceType
    authority_tier: AuthorityTier
    jurisdiction: str = ""
    url: str = ""
    isbn: str = ""
    doi: str = ""
    edition_or_section: str = ""
    rights_note: str = ""
    checked_at: datetime | None = None
    content_hash: str = ""
    active: bool = True
    # graph path only if under approved Logseq root (optional)
    graph_path: str = ""
    notes: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CanonicalSourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    publisher_or_author: str = ""
    source_type: SourceType
    authority_tier: AuthorityTier
    jurisdiction: str = ""
    url: str = ""
    isbn: str = ""
    doi: str = ""
    edition_or_section: str = ""
    rights_note: str = ""
    checked_at: datetime | None = None
    content_hash: str = ""
    active: bool = True
    graph_path: str = ""
    notes: str = ""


class SourceEvidence(BaseModel):
    id: str = Field(default_factory=lambda: f"ev-{uuid4().hex[:12]}")
    source_id: str
    excerpt: str = Field(max_length=2000)
    graph_path: str = ""
    source_location: str = ""
    retrieved_at: datetime
    consultation_id: str | None = None
    content_hash: str = ""


class SourceEvidenceCreate(BaseModel):
    source_id: str
    excerpt: str = Field(min_length=1, max_length=2000)
    graph_path: str = ""
    source_location: str = ""
    consultation_id: str | None = None


class Citation(BaseModel):
    source_id: str
    title: str
    path_or_url: str = ""
    excerpt: str = ""
    authority_tier: AuthorityTier
    evidence_id: str | None = None


class ModelMeta(BaseModel):
    """Kept separate from culinary truth."""

    model: str | None = None
    provider: str | None = None
    used_ai: bool = False
    cost_estimate: str | None = None
    notes: str = ""


class EvidenceGatedResult(BaseModel):
    recommendation: str
    safety_verdict: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    unknowns_or_conflicts: list[str] = Field(default_factory=list)
    research_status: ResearchStatus = ResearchStatus.not_needed
    gate_status: EvidenceGateStatus = EvidenceGateStatus.insufficient_evidence
    model_meta: ModelMeta = Field(default_factory=ModelMeta)
    # rejected claims are not presented as verified
    verified_for_professional_use: bool = False

    @field_validator("confidence")
    @classmethod
    def clamp_conf(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class ConsultationEvidenceBundle(BaseModel):
    consultation_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    gated_result: EvidenceGatedResult | None = None
    research_pending_ids: list[str] = Field(default_factory=list)


# Safety claim keywords that require Tier-1 citation
SAFETY_CLAIM_MARKERS = (
    "allergen",
    "allergens",
    "food safety",
    "haccp",
    "temperature",
    "°c",
    "celsius",
    "storage",
    "shelf life",
    "use by",
    "use-by",
    "legal",
    "legislation",
    "fsa",
    "uk food",
    "core temperature",
    "danger zone",
    "reheat",
    "chill",
    "cross-contamination",
    "cross contamination",
)
