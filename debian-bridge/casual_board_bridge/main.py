"""Outbound-only Debian bridge worker.

Long-polls the hosted API for leased jobs, runs a local executor hook
(Hermes/Linux-Wiki placeholder — not claimed verified), posts signed results.

Never opens a public inbound port.
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
    {
        "status",
        "capture",
        "add_today",
        "remove_today",
        "set_media",
        "set_machine",
    }
)


def sign_result(secret: str, job_id: str, status: str, body: dict[str, Any]) -> str:
    if not secret:
        return "open-dev"
    raw = f"{job_id}|{status}|{json.dumps(body, sort_keys=True, default=str)}"
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


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
            data = r.json()
            return data.get("job")

    def post_result(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any],
        message: str = "",
        board_patch: dict[str, Any] | None = None,
        executor_note: str = "stub — Hermes/mpv not claimed verified",
    ) -> dict[str, Any]:
        sig = sign_result(self.token, job_id, status, result)
        body = {
            "job_id": job_id,
            "status": status,
            "result": result,
            "message": message,
            "worker_id": self.worker_id,
            "signature": sig,
            "executor_note": executor_note,
            "board_patch": board_patch,
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{self.base_url}/v1/bridge/jobs/result",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            return r.json()

    def process_one(self, timeout_s: float = 25.0) -> dict[str, Any] | None:
        job = self.lease(timeout_s=timeout_s)
        if not job:
            return None
        cmd = job.get("command")
        if cmd not in ALLOWLIST:
            return self.post_result(
                job["id"],
                "failed",
                {"error": "not allowlisted"},
                message=f"reject {cmd}",
            )
        try:
            out = self.executor(job)
            status = "completed" if out.get("ok", True) else "failed"
            return self.post_result(
                job["id"],
                status,
                out.get("result") or {},
                message=out.get("message") or status,
                board_patch=out.get("board_patch"),
                executor_note=out.get(
                    "executor_note",
                    "stub — Hermes/mpv not claimed verified",
                ),
            )
        except Exception as e:  # noqa: BLE001
            return self.post_result(
                job["id"],
                "failed",
                {"error": str(e)},
                message=str(e),
            )

    def run_loop(self, interval: float = 0.5) -> None:
        print(f"bridge worker {self.worker_id} → {self.base_url}", flush=True)
        while True:
            try:
                res = self.process_one(timeout_s=25.0)
                if res:
                    print(json.dumps({"job": res.get("id"), "status": res.get("status")}), flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"bridge error: {e}", file=sys.stderr, flush=True)
                time.sleep(interval)


def stub_executor(job: dict[str, Any]) -> dict[str, Any]:
    """Local hook placeholder.

    Wire Linux-Wiki / Hermes here later. Does NOT claim real mpv/Hermes execution.
    For set_machine, returns a synthetic board_patch from payload only.
    """
    cmd = job.get("command")
    payload = job.get("payload") or {}
    if cmd == "set_machine":
        patch = {
            "machine": {
                **payload,
                "freshness": "fresh",
            }
        }
        return {
            "ok": True,
            "message": "stub applied machine patch from payload (not live /proc)",
            "result": {"command": cmd, "stub": True},
            "board_patch": patch,
            "executor_note": "stub — Hermes/mpv not claimed verified",
        }
    if cmd == "set_media":
        return {
            "ok": True,
            "message": "stub media patch",
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
        "message": f"stub handled {cmd}",
        "result": {"command": cmd, "stub": True, "payload": payload},
        "executor_note": "stub — Hermes/mpv not claimed verified",
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Casual Board outbound bridge worker")
    p.add_argument("--url", default=os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090"))
    p.add_argument(
        "--token",
        default=os.environ.get("CASUAL_BOARD_BRIDGE_TOKEN")
        or os.environ.get("CASUAL_BOARD_TOKEN", ""),
    )
    p.add_argument("--worker-id", default=os.environ.get("CASUAL_BOARD_WORKER_ID", "debian-bridge"))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor")
    sub.add_parser("heartbeat")
    sub.add_parser("once")
    sub.add_parser("run")

    args = p.parse_args(argv)
    worker = BridgeWorker(args.url, args.token, worker_id=args.worker_id)

    if args.cmd == "doctor":
        print(
            json.dumps(
                {
                    "url": args.url,
                    "token_set": bool(args.token),
                    "worker_id": args.worker_id,
                    "allowlist": sorted(ALLOWLIST),
                    "note": "Hermes/mpv integration not claimed verified",
                },
                indent=2,
            )
        )
        try:
            print(json.dumps(worker.heartbeat(), indent=2))
        except Exception as e:
            print(f"heartbeat failed: {e}", file=sys.stderr)
            sys.exit(2)
        return

    if args.cmd == "heartbeat":
        print(json.dumps(worker.heartbeat(), indent=2))
        return

    if args.cmd == "once":
        res = worker.process_one(timeout_s=5.0)
        print(json.dumps(res, indent=2))
        return

    if args.cmd == "run":
        worker.run_loop()


if __name__ == "__main__":
    main()
