"""Loopback Graph Recall API client — lease + signed result only."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

log = logging.getLogger("graph_recall_worker.client")


def canonical_result_payload(
    *,
    consultation_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    kitchen_memory: list,
    enrichment: dict,
    message: str,
) -> str:
    obj = {
        "consultation_id": consultation_id,
        "enrichment": enrichment or {},
        "kitchen_memory": kitchen_memory or [],
        "lease_nonce": lease_nonce,
        "message": message or "",
        "status": status,
        "worker_id": worker_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sign_result(
    secret: str,
    *,
    consultation_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    kitchen_memory: list,
    enrichment: dict,
    message: str = "",
) -> str:
    raw = canonical_result_payload(
        consultation_id=consultation_id,
        status=status,
        worker_id=worker_id,
        lease_nonce=lease_nonce,
        kitchen_memory=kitchen_memory,
        enrichment=enrichment,
        message=message,
    )
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


class GraphRecallClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        worker_id: str,
        *,
        timeout_s: float = 30.0,
    ) -> None:
        # Force loopback-safe base (caller responsibility for URL choice)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.worker_id = worker_id
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.token}",
            "content-type": "application/json",
            "accept": "application/json",
        }

    def lease(self, timeout_s: float = 25.0) -> dict[str, Any] | None:
        with httpx.Client(timeout=timeout_s + 15.0) as c:
            r = c.get(
                f"{self.base_url}/v1/graph-recall/jobs/lease",
                headers=self._headers(),
                params={"worker_id": self.worker_id, "timeout_s": timeout_s},
            )
            r.raise_for_status()
            return r.json().get("job")

    def post_result(
        self,
        *,
        consultation_id: str,
        lease_nonce: str,
        status: str,
        kitchen_memory: list | None = None,
        enrichment: dict | None = None,
        message: str = "",
        proposed_guest_service: bool | None = None,
    ) -> dict[str, Any]:
        kitchen_memory = kitchen_memory or []
        enrichment = enrichment or {}
        sig = sign_result(
            self.token,
            consultation_id=consultation_id,
            status=status,
            worker_id=self.worker_id,
            lease_nonce=lease_nonce,
            kitchen_memory=kitchen_memory,
            enrichment=enrichment,
            message=message,
        )
        body = {
            "consultation_id": consultation_id,
            "status": status,
            "kitchen_memory": kitchen_memory,
            "enrichment": enrichment,
            "message": message,
            "worker_id": self.worker_id,
            "lease_nonce": lease_nonce,
            "signature": sig,
            "proposed_guest_service": proposed_guest_service,
        }
        with httpx.Client(timeout=self.timeout_s) as c:
            r = c.post(
                f"{self.base_url}/v1/graph-recall/jobs/result",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            return r.json()
