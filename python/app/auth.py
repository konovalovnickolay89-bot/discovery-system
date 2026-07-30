"""Token auth for Hermes maintainer agent + admin CLI."""

from __future__ import annotations

import hmac
import os
import secrets

from fastapi import Header, HTTPException, status

# Shared secret for Hermes + admin CLI. On Debian: export CASUAL_BOARD_TOKEN=...
# Empty token in dev allows open admin (preview sandbox only).
def configured_token() -> str:
    return os.environ.get("CASUAL_BOARD_TOKEN", "").strip()


def is_open_dev() -> bool:
    """No token set → open mode (Grok Build sandbox / local toy)."""
    return not configured_token()


def verify_bearer(authorization: str | None) -> str:
    """Return actor name if authorized, else raise 401."""
    expected = configured_token()
    if not expected:
        return "dev-open"

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required (Hermes / admin)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    got = authorization[7:].strip()
    if not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "hermes-or-admin"


def require_admin(authorization: str | None = Header(default=None)) -> str:
    return verify_bearer(authorization)


def mint_dev_hint() -> dict[str, str]:
    if is_open_dev():
        return {
            "mode": "open-dev",
            "hint": "Set CASUAL_BOARD_TOKEN on Debian before exposing the API",
        }
    return {"mode": "token", "hint": "Authorization: Bearer <CASUAL_BOARD_TOKEN>"}


def generate_token() -> str:
    return secrets.token_urlsafe(32)
