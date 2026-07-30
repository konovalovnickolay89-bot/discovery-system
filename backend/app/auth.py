"""Token auth for one-owner deployments."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from .config import get_settings

log = logging.getLogger("casual_board.auth")


def auth_mode() -> str:
    return "token" if get_settings().auth_required else "open-dev"


def require_token(authorization: str | None = Header(default=None)) -> str:
    """Return actor label. In open-dev mode accepts anonymous."""
    settings = get_settings()
    expected = settings.api_token.strip()
    if not expected:
        return "open-dev"

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    got = authorization[7:].strip()
    if not hmac.compare_digest(got, expected):
        log.warning("invalid token attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "owner"
