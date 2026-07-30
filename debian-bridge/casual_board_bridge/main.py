"""Outbound-only bridge.

Polls / maintains connection *out* to the hosted API. Never opens a listen port.
Allowlisted commands only; system-changing actions require explicit approval
on the hosted side (require_approval=true).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

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

SYSTEM_CHANGING = frozenset({"set_machine", "set_media", "remove_today"})


class BridgeClient:
    def __init__(self, base_url: str, token: str, auto_approve_safe: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.auto_approve_safe = auto_approve_safe

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json", "accept": "application/json"}
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        return h

    def run_command(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str = "hermes",
        force_approval: bool | None = None,
    ) -> dict[str, Any]:
        if command not in ALLOWLIST:
            raise SystemExit(f"command not allowlisted: {command}")
        require = (
            force_approval
            if force_approval is not None
            else (command in SYSTEM_CHANGING)
        )
        body = {
            "command": command,
            "payload": payload or {},
            "source": "bridge",
            "actor": actor,
            "require_approval": require,
            "client_id": "debian-bridge",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(f"{self.base_url}/v1/commands", headers=self._headers(), json=body)
            r.raise_for_status()
            return r.json()

    def approve(self, action_id: str, approve: bool = True, note: str = "") -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{self.base_url}/v1/actions/{action_id}/approval",
                headers=self._headers(),
                json={"approve": approve, "note": note},
            )
            r.raise_for_status()
            return r.json()

    def heartbeat(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{self.base_url}/health", headers=self._headers())
            r.raise_for_status()
            return r.json()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Casual Board outbound bridge")
    p.add_argument("--url", default=os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090"))
    p.add_argument("--token", default=os.environ.get("CASUAL_BOARD_TOKEN", ""))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor")
    sub.add_parser("heartbeat")
    r = sub.add_parser("run")
    r.add_argument("command", choices=sorted(ALLOWLIST))
    r.add_argument("--payload", default="{}", help="JSON payload")
    r.add_argument("--approve", action="store_true", help="auto-approve if pending")
    r.add_argument("--actor", default="hermes")

    poll = sub.add_parser("poll-machine")
    poll.add_argument("--interval", type=float, default=60.0)
    poll.add_argument("--disk", type=float, default=None)
    poll.add_argument("--approve", action="store_true")

    args = p.parse_args(argv)
    client = BridgeClient(args.url, args.token)

    if args.cmd == "doctor":
        print(json.dumps({"url": args.url, "token_set": bool(args.token), "allowlist": sorted(ALLOWLIST)}, indent=2))
        try:
            print(json.dumps(client.heartbeat(), indent=2))
        except Exception as e:
            print(f"heartbeat failed: {e}", file=sys.stderr)
            sys.exit(2)
        return

    if args.cmd == "heartbeat":
        print(json.dumps(client.heartbeat(), indent=2))
        return

    if args.cmd == "run":
        payload = json.loads(args.payload)
        res = client.run_command(args.command, payload, actor=args.actor)
        print(json.dumps(res, indent=2))
        action = res.get("action") or {}
        if action.get("status") == "pending_approval" and args.approve:
            res2 = client.approve(action["id"], True, note="bridge --approve")
            print(json.dumps(res2, indent=2))
        return

    if args.cmd == "poll-machine":
        # Example outbound reporter — replace with real /proc reads on Debian
        while True:
            payload = {
                "disk_pct": args.disk if args.disk is not None else 42.0,
                "free_gib": 100.0,
                "failed_units": 0,
                "net": "wired",
                "apt_updates": 0,
                "host": "debian-minimal",
            }
            try:
                res = client.run_command("set_machine", payload, actor="machine-poller")
                print(json.dumps({"ts": time.time(), "status": res.get("action", {}).get("status")}, indent=2))
                action = res.get("action") or {}
                if action.get("status") == "pending_approval" and args.approve:
                    client.approve(action["id"], True, note="poll-machine")
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
