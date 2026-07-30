"""Outbound Debian bridge: long-poll lease, signed results with lease_nonce.

Hermes/mpv not claimed verified — stub executor only.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from typing import Any, Callable

import httpx

ALLOWLIST = frozenset(
    {"status", "capture", "add_today", "remove_today", "set_media", "set_machine"}
)


def canonical_payload(
    *,
    job_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    result: dict[str, Any],
    message: str,
    board_patch: dict[str, Any] | None,
) -> str:
    obj = {
        "board_patch": board_patch if board_patch is not None else None,
        "job_id": job_id,
        "lease_nonce": lease_nonce,
        "message": message or "",
        "result": result or {},
        "status": status,
        "worker_id": worker_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sign_result(
    secret: str,
    *,
    job_id: str,
    status: str,
    worker_id: str,
    lease_nonce: str,
    result: dict[str, Any],
    message: str = "",
    board_patch: dict[str, Any] | None = None,
) -> str:
    raw = canonical_payload(
        job_id=job_id,
        status=status,
        worker_id=worker_id,
        lease_nonce=lease_nonce,
        result=result,
        message=message,
        board_patch=board_patch,
    )
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def stub_executor(job: dict[str, Any]) -> dict[str, Any]:
    cmd = job.get("command")
    payload = job.get("payload") or {}
    if cmd == "set_machine":
        return {
            "ok": True,
            "message": "stub machine patch (not live /proc)",
            "result": {"command": cmd, "stub": True},
            "board_patch": {"machine": {**payload, "freshness": "fresh"}},
            "executor_note": "stub — Hermes/mpv not claimed verified",
        }
    if cmd == "set_media":
        return {
            "ok": True,
            "message": "stub media",
            "result": {"command": cmd, "stub": True},
            "board_patch": {"media": payload},
            "executor_note": "stub — Hermes/mpv not claimed verified",
        }
    if cmd == "remove_today":
        return {
            "ok": True,
            "message": f"stub remove {payload.get('id')}",
            "result": {"command": cmd, "stub": True},
            "board_patch": {"remove_today_id": payload.get("id")},
            "executor_note": "stub — Hermes/mpv not claimed verified",
        }
    return {
        "ok": True,
        "message": f"stub {cmd}",
        "result": {"command": cmd, "stub": True},
        "executor_note": "stub — Hermes/mpv not claimed verified",
    }


class BridgeWorker:
    def __init__(
        self,
        base_url: str,
        token: str,
        worker_id: str = "debian-bridge",
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.worker_id = worker_id
        self.executor = executor or stub_executor

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json", "accept": "application/json"}
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        return h

    def heartbeat(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{self.base_url}/health", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def lease(self, timeout_s: float = 25.0) -> dict[str, Any] | None:
        with httpx.Client(timeout=timeout_s + 10.0) as c:
            r = c.get(
                f"{self.base_url}/v1/bridge/jobs/lease",
                headers=self._headers(),
                params={"worker_id": self.worker_id, "timeout_s": timeout_s},
            )
            r.raise_for_status()
            return r.json().get("job")

    def post_result(
        self,
        job: dict[str, Any],
        status: str,
        result: dict[str, Any],
        message: str = "",
        board_patch: dict[str, Any] | None = None,
        executor_note: str = "stub — Hermes/mpv not claimed verified",
    ) -> dict[str, Any]:
        job_id = job["id"]
        nonce = job.get("lease_nonce") or ""
        sig = sign_result(
            self.token,
            job_id=job_id,
            status=status,
            worker_id=self.worker_id,
            lease_nonce=nonce,
            result=result,
            message=message,
            board_patch=board_patch,
        )
        body = {
            "job_id": job_id,
            "status": status,
            "result": result,
            "message": message,
            "worker_id": self.worker_id,
            "lease_nonce": nonce,
            "signature": sig,
            "executor_note": executor_note,
            "board_patch": board_patch,
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(f"{self.base_url}/v1/bridge/jobs/result", headers=self._headers(), json=body)
            r.raise_for_status()
            return r.json()

    def process_one(self, timeout_s: float = 25.0) -> dict[str, Any] | None:
        job = self.lease(timeout_s=timeout_s)
        if not job:
            return None
        if job.get("command") not in ALLOWLIST:
            return self.post_result(job, "failed", {"error": "not allowlisted"}, message="reject")
        try:
            out = self.executor(job)
            status = "completed" if out.get("ok", True) else "failed"
            return self.post_result(
                job,
                status,
                out.get("result") or {},
                message=out.get("message") or status,
                board_patch=out.get("board_patch"),
                executor_note=out.get("executor_note", "stub — Hermes/mpv not claimed verified"),
            )
        except Exception as e:  # noqa: BLE001
            return self.post_result(job, "failed", {"error": str(e)}, message=str(e))

    def run_loop(self) -> None:
        print(f"bridge worker {self.worker_id} → {self.base_url}", flush=True)
        while True:
            try:
                res = self.process_one(timeout_s=25.0)
                if res:
                    print(json.dumps({"job": res.get("id"), "status": res.get("status")}), flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"bridge error: {e}", file=sys.stderr, flush=True)
                time.sleep(1.0)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090"))
    p.add_argument("--token", default=os.environ.get("CASUAL_BOARD_BRIDGE_TOKEN", ""))
    p.add_argument("--worker-id", default=os.environ.get("CASUAL_BOARD_WORKER_ID", "debian-bridge"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("once")
    sub.add_parser("run")
    args = p.parse_args(argv)
    w = BridgeWorker(args.url, args.token, worker_id=args.worker_id)
    if args.cmd == "doctor":
        print(json.dumps({"url": args.url, "token_set": bool(args.token), "worker_id": args.worker_id}, indent=2))
        print(json.dumps(w.heartbeat(), indent=2))
        return
    if args.cmd == "once":
        print(json.dumps(w.process_one(timeout_s=5.0), indent=2))
        return
    w.run_loop()


if __name__ == "__main__":
    main()
