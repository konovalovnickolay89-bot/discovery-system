"""Server-only credentials: owner (admin) and bridge. Never used by browser."""

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
    settings = get_settings()
    expected = settings.api_token.strip()
    if not expected:
        return "open-dev"
    got = _bearer(authorization)
    if not got:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if settings.bridge_token and hmac.compare_digest(got, settings.bridge_token):
        raise HTTPException(status_code=403, detail="bridge token cannot call owner routes")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "owner"


def require_bridge(authorization: str | None = Header(default=None)) -> str:
    settings = get_settings()
    expected = settings.bridge_token.strip()
    if not expected:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="bridge token not configured")
        return "open-dev-bridge"
    got = _bearer(authorization)
    if not got:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bridge Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if settings.api_token and hmac.compare_digest(got, settings.api_token):
        raise HTTPException(status_code=403, detail="owner token cannot call bridge routes")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bridge Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "bridge"
