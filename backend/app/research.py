"""Optional allowlisted research fallback. Findings are pending_review only — never auto-canonical."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from .config import get_settings
from .evidence_models import (
    AuthorityTier,
    CanonicalSource,
    ResearchStatus,
    SourceType,
)
from .evidence_store import content_hash, create_evidence, save_source
from .evidence_models import SourceEvidenceCreate

log = logging.getLogger("casual_board.research")

# FetchFn(url) -> text  (tests inject fake)
FetchFn = Callable[[str], str]

DEFAULT_ALLOWLIST = (
    "www.food.gov.uk",
    "food.gov.uk",
    "www.foodstandards.gov.scot",
    "www.fsai.ie",
)


def research_domain_allowlist() -> set[str]:
    s = get_settings()
    raw = getattr(s, "research_allowlist_domains", "") or ""
    if not raw.strip():
        return set(DEFAULT_ALLOWLIST)
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


def url_allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        allowed = research_domain_allowlist()
        return host in allowed or any(host.endswith("." + d) for d in allowed)
    except Exception:  # noqa: BLE001
        return False


def _sanitise_query(q: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9 ,.\-]", " ", q or "")
    s = re.sub(r"\s+", " ", s).strip()[:120]
    return s or "food safety"


def build_research_urls(query: str) -> list[str]:
    """Official-first URLs (allowlisted). No tokens."""
    q = _sanitise_query(query)
    # FSA search-style landing — still only allowlisted host
    urls = [
        f"https://www.food.gov.uk/search?keywords={q.replace(' ', '+')}",
        "https://www.food.gov.uk/business-guidance/allergen-guidance-for-food-businesses",
        "https://www.food.gov.uk/safety-hygiene",
    ]
    return [u for u in urls if url_allowed(u)]


def fetch_research_pending(
    query: str,
    *,
    consultation_id: str | None = None,
    fetcher: FetchFn | None = None,
    max_pages: int = 2,
) -> tuple[ResearchStatus, list[str], list[dict[str, Any]]]:
    """
    Fetch allowlisted pages as untrusted data; save as pending_review sources.
    Never elevates to active canonical kitchen knowledge automatically.
    """
    if fetcher is None:
        # No network in default path without explicit enable
        s = get_settings()
        if not getattr(s, "research_enabled", False):
            return ResearchStatus.unavailable, [], []
        # Real fetch only when enabled — still no secrets to browser
        def _http(url: str) -> str:
            import urllib.request

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "CasualBoardResearch/1.0 (pending-review only)"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
                return resp.read(8000).decode("utf-8", "replace")

        fetcher = _http

    pending_ids: list[str] = []
    findings: list[dict[str, Any]] = []
    urls = build_research_urls(query)[: max(1, min(max_pages, 3))]
    if not urls:
        return ResearchStatus.unavailable, [], []

    for url in urls:
        if not url_allowed(url):
            continue
        try:
            text = fetcher(url)
        except Exception as e:  # noqa: BLE001
            log.info("research_fetch_failed category=%s", type(e).__name__)
            continue
        # Treat as untrusted data blob — strip tags lightly
        plain = re.sub(r"<[^>]+>", " ", text or "")
        plain = re.sub(r"\s+", " ", plain).strip()[:1500]
        if not plain:
            continue
        # Save as inactive pending source (not auto-canonical kitchen knowledge)
        src = save_source(
            CanonicalSource(
                title=f"Research pending review: {urlparse(url).path or url}",
                publisher_or_author=urlparse(url).hostname or "",
                source_type=SourceType.research_fetch,
                authority_tier=AuthorityTier.tier_1_official
                if "food.gov.uk" in url
                else AuthorityTier.tier_4_research,
                jurisdiction="UK" if "food.gov.uk" in url else "",
                url=url,
                rights_note="Fetched for pending human review — not auto-approved kitchen knowledge",
                checked_at=datetime.now(timezone.utc),
                content_hash=content_hash(plain),
                active=False,  # not usable as verified citation until activated
                notes="pending_review research fallback; page is untrusted data",
            )
        )
        create_evidence(
            SourceEvidenceCreate(
                source_id=src.id,
                excerpt=plain[:800],
                source_location=url,
                consultation_id=consultation_id,
            )
        )
        pending_ids.append(src.id)
        findings.append(
            {
                "source_id": src.id,
                "url": url,
                "excerpt": plain[:400],
                "status": "pending_review",
                "untrusted_data": True,
            }
        )

    if not pending_ids:
        return ResearchStatus.unavailable, [], []
    return ResearchStatus.pending_review, pending_ids, findings
