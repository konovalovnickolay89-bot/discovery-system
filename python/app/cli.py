#!/usr/bin/env python3
"""Casual Board CLI — Debian terminal dashboard + commands.

Examples:
  python -m app.cli status
  python -m app.cli dash
  python -m app.cli watch
  python -m app.cli capture "check duck confit Friday"
  python -m app.cli media play
  python -m app.cli hermes status

Env:
  CASUAL_BOARD_URL   default http://127.0.0.1:8090
  CASUAL_BOARD_TOKEN Bearer for admin/hermes routes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = os.environ.get("CASUAL_BOARD_URL", "http://127.0.0.1:8090").rstrip("/")
TOKEN = os.environ.get("CASUAL_BOARD_TOKEN", "").strip()


def _headers(admin: bool = False) -> dict[str, str]:
    h = {"content-type": "application/json", "accept": "application/json"}
    if admin and TOKEN:
        h["authorization"] = f"Bearer {TOKEN}"
    elif admin and not TOKEN:
        # open-dev mode — still send nothing
        pass
    return h


def api(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    admin: bool = False,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{DEFAULT_URL}{path}",
        data=data,
        headers=_headers(admin=admin),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"API unreachable at {DEFAULT_URL}: {e}", file=sys.stderr)
        sys.exit(2)


def cmd_status(_: argparse.Namespace) -> None:
    h = api("GET", "/api/health")
    b = api("GET", "/api/board")
    print(f"host     {b['header']['host']}")
    print(f"status   {b['header']['status']['label']}")
    print(f"updated  {b['header']['updated_at']}")
    print(f"seq      {h.get('seq')}")
    print(f"engine   {h.get('engine')} · pydantic {h.get('pydantic')}")
    print(f"auth     {h.get('auth', {}).get('mode')}")
    print(f"data     {h.get('data_path')}")
    m = b["media"]
    print(
        f"media    {m['state']} · {m.get('current', {}).get('title', '—')} · "
        f"cassette={'on' if m['cassette'] else 'off'} · vol {m['volume']}"
    )
    print(f"path     {m.get('path_label')}")


def _line(s: str = "") -> None:
    print(s)


def cmd_dash(_: argparse.Namespace) -> None:
    b = api("GET", "/api/board")
    h = b["header"]
    _line("┌─ casual board ─────────────────────────────────────")
    _line(f"│ {h['host']} · {h['status']['label']}")
    _line(f"│ updated {h['updated_at']}")
    _line("├─ today ────────────────────────────────────────────")
    for it in b["today"]["items"][:8]:
        mark = "!" if it.get("level") == "warn" else "·"
        _line(f"│ {mark} {it['text'][:72]}")
    _line("├─ media ────────────────────────────────────────────")
    m = b["media"]
    cur = m.get("current") or {}
    _line(f"│ [{m['state']}] {cur.get('title', '—')} · {cur.get('artist', '')}")
    _line(f"│ {m.get('path_label')} · vol {m['volume']}")
    _line("├─ machine ──────────────────────────────────────────")
    mc = b["machine"]
    _line(
        f"│ disk {mc['disk_pct']}% · free {mc['free_gib']}G · "
        f"failed {mc['failed_units']} · {mc['net']} · apt {mc['apt_updates']}"
    )
    _line("├─ learning (window) ────────────────────────────────")
    pool = b["learning"]["pool"][:3]
    for it in pool:
        _line(f"│ · {it['primary'][:70]}")
    _line("└────────────────────────────────────────────────────")


def cmd_watch(args: argparse.Namespace) -> None:
    """Poll dashboard (WS-free; works anywhere). Ctrl+C to stop."""
    interval = max(1.0, float(args.interval))
    last_seq = -1
    try:
        while True:
            h = api("GET", "/api/health")
            seq = int(h.get("seq") or 0)
            if seq != last_seq:
                last_seq = seq
                # clear-ish
                print("\033[2J\033[H", end="")
                print(f"watch seq={seq} every {interval}s · {DEFAULT_URL}")
                cmd_dash(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nbye")


def cmd_capture(args: argparse.Namespace) -> None:
    note = " ".join(args.note).strip()
    if not note:
        print("note required", file=sys.stderr)
        sys.exit(1)
    res = api("POST", "/api/ai/capture", {"note": note, "source": "cli"})
    draft = res["draft"]
    print(f"capture · {draft['title']}")
    print(f"  {draft['body']}")
    print(f"  tags={draft['tags']} level={draft['level']}")


def cmd_media(args: argparse.Namespace) -> None:
    cmd = args.command
    body: dict[str, Any] = {"command": cmd, "source": "cli"}
    if cmd == "volume":
        if args.volume is None:
            print("volume needs --volume N", file=sys.stderr)
            sys.exit(1)
        body["volume"] = args.volume
    # map cassette on/off
    if cmd == "cassette-on":
        body["command"] = "cassette_on"
    if cmd == "cassette-off":
        body["command"] = "cassette_off"
    res = api("POST", "/api/media/command", body)
    print(res.get("note") or res)


def cmd_hermes(args: argparse.Namespace) -> None:
    action = args.action
    payload: dict[str, Any] = {}
    if action == "add_today" and args.text:
        payload["text"] = args.text
    if action == "remove_today" and args.id:
        payload["id"] = args.id
    if action == "capture" and args.text:
        payload["note"] = args.text
    res = api(
        "POST",
        "/api/hermes",
        {"action": action, "payload": payload, "agent": "cli-hermes"},
        admin=True,
    )
    print(res.get("message") or res)
    if args.json and res.get("board"):
        print(json.dumps(res["board"], indent=2)[:2000])


def cmd_reset(_: argparse.Namespace) -> None:
    b = api("POST", "/api/board/reset", {}, admin=True)
    print(f"reset ok · host {b['header']['host']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casual-board", description="Casual Board CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="compact status").set_defaults(func=cmd_status)
    sub.add_parser("dash", help="text dashboard").set_defaults(func=cmd_dash)

    w = sub.add_parser("watch", help="refreshing dashboard")
    w.add_argument("--interval", default=2.0, type=float)
    w.set_defaults(func=cmd_watch)

    c = sub.add_parser("capture", help="AI-structure a note into today")
    c.add_argument("note", nargs="+")
    c.set_defaults(func=cmd_capture)

    m = sub.add_parser("media", help="mpv/ytdl/cassette transport")
    m.add_argument(
        "command",
        choices=["play", "pause", "next", "stop", "cassette-on", "cassette-off", "volume"],
    )
    m.add_argument("--volume", type=int, default=None)
    m.set_defaults(func=cmd_media)

    h = sub.add_parser("hermes", help="maintainer-agent actions (token)")
    h.add_argument(
        "action",
        choices=[
            "ping",
            "status",
            "reset_board",
            "add_today",
            "remove_today",
            "capture",
        ],
    )
    h.add_argument("--text", default="")
    h.add_argument("--id", default="")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_hermes)

    sub.add_parser("reset", help="reset board seed (admin)").set_defaults(func=cmd_reset)
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
