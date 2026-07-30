"""Durable SQLite registry for canonical sources + evidence links."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import dumps, get_conn, loads
from .evidence_models import (
    AuthorityTier,
    CanonicalSource,
    CanonicalSourceCreate,
    Citation,
    SourceEvidence,
    SourceEvidenceCreate,
    SourceType,
)

# Paths like /Users/... are never canonical citations
_LEGACY_PATH = re.compile(
    r"^/(Users|home/(?!discovery-system)|var/folders|tmp|private)/",
    re.I,
)
APPROVED_GRAPH_ROOT = "/home/discovery-system/Logseq/graph"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def is_legacy_local_path(path: str) -> bool:
    p = (path or "").strip()
    if not p:
        return False
    if _LEGACY_PATH.search(p):
        return True
    if p.startswith("/Users/"):
        return True
    return False


def is_approved_graph_path(path: str) -> bool:
    p = (path or "").strip()
    if not p:
        return False
    try:
        from pathlib import Path

        root = Path(APPROVED_GRAPH_ROOT).resolve()
        cand = Path(p).expanduser()
        if not cand.is_absolute():
            cand = root / cand
        resolved = cand.resolve()
        return str(resolved).startswith(str(root) + "/") or str(resolved) == str(root)
    except Exception:  # noqa: BLE001
        return p.startswith(APPROVED_GRAPH_ROOT)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:32]


def save_source(src: CanonicalSource) -> CanonicalSource:
    now = _now()
    if not src.created_at:
        src = src.model_copy(update={"created_at": now})
    src = src.model_copy(update={"updated_at": now})
    if not src.content_hash:
        src = src.model_copy(
            update={"content_hash": content_hash(f"{src.title}|{src.url}|{src.graph_path}|{src.doi}")}
        )
    get_conn().execute(
        """
        INSERT INTO canonical_sources(id, data_json, active, authority_tier, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          data_json=excluded.data_json,
          active=excluded.active,
          authority_tier=excluded.authority_tier,
          updated_at=excluded.updated_at
        """,
        (
            src.id,
            dumps(src.model_dump(mode="json")),
            1 if src.active else 0,
            int(src.authority_tier.value),
            _iso(src.updated_at),
        ),
    )
    get_conn().commit()
    return src


def create_source(body: CanonicalSourceCreate) -> CanonicalSource:
    # Migrate legacy paths as unverified only
    graph_path = body.graph_path or ""
    notes = body.notes or ""
    st = body.source_type
    tier = body.authority_tier
    if is_legacy_local_path(graph_path) or is_legacy_local_path(body.url):
        st = SourceType.legacy_unverified
        tier = AuthorityTier.tier_5_inspiration
        notes = (notes + " | migrated as unverified legacy path").strip(" |")
        graph_path = ""  # do not treat as citation path
    src = CanonicalSource(
        title=body.title,
        publisher_or_author=body.publisher_or_author,
        source_type=st,
        authority_tier=tier,
        jurisdiction=body.jurisdiction,
        url=body.url if not is_legacy_local_path(body.url) else "",
        isbn=body.isbn,
        doi=body.doi,
        edition_or_section=body.edition_or_section,
        rights_note=body.rights_note,
        checked_at=body.checked_at,
        content_hash=body.content_hash,
        active=body.active,
        graph_path=graph_path if is_approved_graph_path(graph_path) else "",
        notes=notes,
    )
    return save_source(src)


def get_source(source_id: str) -> CanonicalSource | None:
    row = get_conn().execute(
        "SELECT data_json FROM canonical_sources WHERE id=?", (source_id,)
    ).fetchone()
    if not row:
        return None
    return CanonicalSource.model_validate(loads(row["data_json"]))


def list_sources(*, active_only: bool = True) -> list[CanonicalSource]:
    if active_only:
        rows = get_conn().execute(
            "SELECT data_json FROM canonical_sources WHERE active=1 ORDER BY authority_tier ASC, updated_at DESC"
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT data_json FROM canonical_sources ORDER BY authority_tier ASC, updated_at DESC"
        ).fetchall()
    return [CanonicalSource.model_validate(loads(r["data_json"])) for r in rows]


def save_evidence(ev: SourceEvidence) -> SourceEvidence:
    get_conn().execute(
        """
        INSERT INTO source_evidence(id, source_id, consultation_id, data_json, retrieved_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          data_json=excluded.data_json,
          source_id=excluded.source_id,
          consultation_id=excluded.consultation_id
        """,
        (
            ev.id,
            ev.source_id,
            ev.consultation_id,
            dumps(ev.model_dump(mode="json")),
            _iso(ev.retrieved_at),
        ),
    )
    get_conn().commit()
    return ev


def create_evidence(body: SourceEvidenceCreate) -> SourceEvidence:
    if not get_source(body.source_id):
        raise ValueError("source_id not found")
    gp = body.graph_path or ""
    if gp and is_legacy_local_path(gp):
        gp = ""
    if gp and not is_approved_graph_path(gp):
        gp = ""
    ev = SourceEvidence(
        source_id=body.source_id,
        excerpt=body.excerpt[:2000],
        graph_path=gp,
        source_location=body.source_location,
        retrieved_at=_now(),
        consultation_id=body.consultation_id,
        content_hash=content_hash(body.excerpt),
    )
    return save_evidence(ev)


def list_evidence_for_consultation(consultation_id: str) -> list[SourceEvidence]:
    rows = get_conn().execute(
        "SELECT data_json FROM source_evidence WHERE consultation_id=? ORDER BY retrieved_at DESC",
        (consultation_id,),
    ).fetchall()
    return [SourceEvidence.model_validate(loads(r["data_json"])) for r in rows]


def link_consultation_evidence(
    consultation_id: str,
    *,
    evidence_ids: list[str],
    source_ids: list[str],
    gated_result: dict[str, Any] | None,
    research_pending_ids: list[str] | None = None,
) -> None:
    get_conn().execute(
        """
        INSERT INTO consultation_evidence(consultation_id, data_json, updated_at)
        VALUES (?,?,?)
        ON CONFLICT(consultation_id) DO UPDATE SET
          data_json=excluded.data_json,
          updated_at=excluded.updated_at
        """,
        (
            consultation_id,
            dumps(
                {
                    "consultation_id": consultation_id,
                    "evidence_ids": evidence_ids,
                    "source_ids": source_ids,
                    "gated_result": gated_result,
                    "research_pending_ids": research_pending_ids or [],
                }
            ),
            _iso(_now()),
        ),
    )
    get_conn().commit()


def get_consultation_evidence(consultation_id: str) -> dict[str, Any] | None:
    row = get_conn().execute(
        "SELECT data_json FROM consultation_evidence WHERE consultation_id=?",
        (consultation_id,),
    ).fetchone()
    if not row:
        return None
    return loads(row["data_json"])


def ensure_source_for_graph_hit(
    *,
    title: str,
    path: str,
    excerpt: str,
    consultation_id: str | None = None,
) -> tuple[CanonicalSource | None, SourceEvidence | None]:
    """Register approved graph path as internal Logseq card (tier 2) or legacy unverified."""
    if is_legacy_local_path(path):
        src = save_source(
            CanonicalSource(
                title=title or "Legacy path",
                source_type=SourceType.legacy_unverified,
                authority_tier=AuthorityTier.tier_5_inspiration,
                notes="unverified legacy local path — not a canonical citation",
                active=True,
            )
        )
        # evidence without path
        ev = create_evidence(
            SourceEvidenceCreate(
                source_id=src.id,
                excerpt=(excerpt or title or "legacy")[:500],
                consultation_id=consultation_id,
            )
        )
        return src, ev

    if not is_approved_graph_path(path):
        return None, None

    # Reuse source by graph_path if present
    for s in list_sources(active_only=False):
        if s.graph_path == path and s.active:
            ev = create_evidence(
                SourceEvidenceCreate(
                    source_id=s.id,
                    excerpt=(excerpt or title)[:500],
                    graph_path=path,
                    source_location=path,
                    consultation_id=consultation_id,
                )
            )
            return s, ev

    src = save_source(
        CanonicalSource(
            title=title or path.rsplit("/", 1)[-1],
            publisher_or_author="Logseq kitchen graph",
            source_type=SourceType.logseq_card,
            authority_tier=AuthorityTier.tier_2_internal,
            graph_path=path,
            checked_at=_now(),
            content_hash=content_hash(path + excerpt),
            active=True,
            notes="auto-registered from approved graph path",
        )
    )
    ev = create_evidence(
        SourceEvidenceCreate(
            source_id=src.id,
            excerpt=(excerpt or title)[:500],
            graph_path=path,
            source_location=path,
            consultation_id=consultation_id,
        )
    )
    return src, ev


def citation_from_source(src: CanonicalSource, excerpt: str = "", evidence_id: str | None = None) -> Citation:
    loc = src.graph_path or src.url or src.doi or ""
    return Citation(
        source_id=src.id,
        title=src.title,
        path_or_url=loc,
        excerpt=excerpt[:500],
        authority_tier=src.authority_tier,
        evidence_id=evidence_id,
    )


def seed_official_fsa_placeholder() -> CanonicalSource:
    """Register UK FSA as Tier-1 template (URL only; content fetched only via research module)."""
    for s in list_sources(active_only=False):
        if "food.gov.uk" in (s.url or ""):
            return s
    return save_source(
        CanonicalSource(
            title="UK Food Standards Agency guidance",
            publisher_or_author="Food Standards Agency",
            source_type=SourceType.official_authority,
            authority_tier=AuthorityTier.tier_1_official,
            jurisdiction="UK",
            url="https://www.food.gov.uk/",
            rights_note="Official UK authority — use for safety/allergen guidance",
            checked_at=_now(),
            active=True,
            notes="registry seed; pages saved as pending_review until human approval",
        )
    )
