"""Server-only credentials: owner, host bridge, graph recall. Never browser."""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from .config import get_settings

log = logging.getLogger("casual_board.auth")


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
    if settings.graph_recall_token and hmac.compare_digest(got, settings.graph_recall_token):
        raise HTTPException(status_code=403, detail="graph recall token cannot call owner routes")
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
    if settings.graph_recall_token and hmac.compare_digest(got, settings.graph_recall_token):
        raise HTTPException(status_code=403, detail="graph recall token cannot call host bridge routes")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bridge Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "bridge"


def require_graph_recall(authorization: str | None = Header(default=None)) -> str:
    settings = get_settings()
    expected = settings.graph_recall_token.strip()
    if not expected:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="graph recall token not configured")
        return "open-dev-graph-recall"
    got = _bearer(authorization)
    if not got:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Graph Recall Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if settings.api_token and hmac.compare_digest(got, settings.api_token):
        raise HTTPException(status_code=403, detail="owner token cannot call graph recall routes")
    if settings.bridge_token and hmac.compare_digest(got, settings.bridge_token):
        raise HTTPException(status_code=403, detail="host bridge token cannot call graph recall routes")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Graph Recall Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "graph-recall"
