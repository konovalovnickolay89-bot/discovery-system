"""Token auth. Owner and bridge secrets never ship to the browser."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from .config import get_settings

log = logging.getLogger("casual_board.auth")


def auth_mode() -> str:
    return "token" if get_settings().auth_required else "open-dev"


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip()


def require_owner(authorization: str | None = Header(default=None)) -> str:
    """Admin / approval routes. CASUAL_BOARD_TOKEN only — not for browsers."""
    settings = get_settings()
    expected = settings.api_token.strip()
    if not expected:
        return "open-dev"
    got = _bearer(authorization)
    if not got or not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "owner"


def require_bridge(authorization: str | None = Header(default=None)) -> str:
    """Debian bridge long-poll + result posting. CASUAL_BOARD_BRIDGE_TOKEN (or TOKEN)."""
    settings = get_settings()
    expected = (settings.bridge_token or settings.api_token).strip()
    if not expected:
        return "open-dev-bridge"
    got = _bearer(authorization)
    if not got or not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bridge Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "bridge"


def optional_owner(authorization: str | None = Header(default=None)) -> str:
    """Label actor if owner token present; otherwise 'public'."""
    settings = get_settings()
    expected = settings.api_token.strip()
    if not expected:
        return "open-dev"
    got = _bearer(authorization)
    if got and hmac.compare_digest(got, expected):
        return "owner"
    return "public"
