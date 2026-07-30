"""Short-lived browser session tokens (HMAC). Distinct from owner/bridge secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Header, HTTPException, status

from .config import get_settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def session_secret() -> str:
    s = get_settings()
    # Prefer dedicated secret; never reuse bridge token for browser sessions
    raw = (s.session_secret or s.api_token or "").strip()
    if not raw:
        # open-dev only
        return "open-dev-session-secret"
    return raw


def issue_session(
    *,
    subject: str = "owner-ui",
    scope: str = "board:rw",
    ttl_s: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    ttl = ttl_s if ttl_s is not None else settings.session_ttl_s
    now = int(time.time())
    payload = {
        "sub": subject,
        "scope": scope,
        "iat": now,
        "exp": now + max(60, ttl),
        "jti": secrets.token_hex(16),
        "typ": "session",
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(session_secret().encode(), body.encode(), hashlib.sha256).digest()
    token = f"{body}.{_b64(sig)}"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": max(60, ttl),
        "scope": scope,
        "expires_at": payload["exp"],
    }


def verify_session(token: str) -> dict[str, Any]:
    try:
        body, sig_b64 = token.split(".", 1)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="malformed session token") from e
    expected = hmac.new(session_secret().encode(), body.encode(), hashlib.sha256).digest()
    try:
        got = _b64d(sig_b64)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="invalid session signature") from e
    if not hmac.compare_digest(expected, got):
        raise HTTPException(status_code=401, detail="invalid session signature")
    try:
        payload = json.loads(_b64d(body))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="invalid session payload") from e
    if payload.get("typ") != "session":
        raise HTTPException(status_code=401, detail="wrong token type")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="session expired")
    scope = str(payload.get("scope") or "")
    if "board:rw" not in scope and "board:r" not in scope:
        raise HTTPException(status_code=403, detail="insufficient session scope")
    return payload


def require_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Browser session required for private board read/write."""
    settings = get_settings()
    if not settings.auth_required and not settings.ui_password.strip():
        # open-dev: no password configured
        return {"sub": "open-dev", "scope": "board:rw", "typ": "session"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    # Reject if someone tries to use owner/bridge raw secrets as session
    if settings.api_token and hmac.compare_digest(token, settings.api_token):
        raise HTTPException(status_code=401, detail="owner token cannot be used as session")
    if settings.bridge_token and hmac.compare_digest(token, settings.bridge_token):
        raise HTTPException(status_code=401, detail="bridge token cannot be used as session")
    return verify_session(token)


def login_with_password(password: str) -> dict[str, Any]:
    settings = get_settings()
    expected = settings.ui_password.strip()
    if not expected:
        if not settings.auth_required:
            return issue_session(subject="open-dev")
        raise HTTPException(status_code=503, detail="UI password not configured")
    if not hmac.compare_digest(password, expected):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return issue_session(subject="ui-user")
