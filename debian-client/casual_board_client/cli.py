"""CLI: status, dash, watch, sync, capture, doctor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from .adapter import NullLocalDashboardAdapter
from .api import BoardApiClient
from .cache import SnapshotCache
from .models import BoardSnapshot


def _print_dash(b: BoardSnapshot, *, offline: bool = False) -> None:
    meta = b.meta
    flag = " [cached/offline]" if offline else ""
    print("┌─ casual board" + flag + " " + "─" * 20)
    print(f"│ rev {b.revision} · {b.status_label}")
    print(f"│ updated {meta.get('updated_at')}")
    print("├─ today ─")
    for it in (b.today.get("items") or [])[:8]:
        mark = "!" if it.get("level") == "warn" else "·"
        print(f"│ {mark} {str(it.get('text', ''))[:72]}")
    print("├─ media ─")
    m = b.media or {}
    cur = m.get("current") or {}
    print(f"│ [{m.get('state')}] {cur.get('title', '—')} · vol {m.get('volume')}")
    print(f"│ {m.get('path_label')}")
    print("├─ machine ─")
    mc = b.machine or {}
    print(
        f"│ disk {mc.get('disk_pct')}% · free {mc.get('free_gib')}G · "
        f"failed {mc.get('failed_units')} · {mc.get('net')} · apt {mc.get('apt_updates')}"
    )
    print("└" + "─" * 40)


def cmd_status(client: BoardApiClient) -> None:
    try:
        h = client.health()
        b = client.get_board()
        offline = False
    except Exception as e:
        b = client.cache.load()
        if not b:
            print(f"unreachable and no cache: {e}", file=sys.stderr)
            sys.exit(2)
        print(f"offline · using cache ({e})", file=sys.stderr)
        offline = True
        h = {}
    print(f"api      {client.base_url}")
    print(f"health   {h.get('ok', 'n/a')} · auth {h.get('auth_mode', '?')}")
    print(f"revision {b.revision}")
    print(f"status   {b.status_label}")
    print(f"cache    {client.cache.path}")
    if offline:
        print("mode     offline-cache")


def cmd_dash(client: BoardApiClient) -> None:
    try:
        b = client.get_board()
        _print_dash(b, offline=False)
    except Exception:
        b = client.cache.load()
        if not b:
            raise
        _print_dash(b, offline=True)


def cmd_sync(client: BoardApiClient) -> None:
    b = client.get_board()
    adapter = NullLocalDashboardAdapter()
    report = adapter.apply_snapshot(b)
    print(json.dumps({"revision": b.revision, "adapter": report}, indent=2))


def cmd_capture(client: BoardApiClient, note: str) -> None:
    res = client.capture(note)
    draft = res.get("draft") or {}
    print(f"capture · {draft.get('title')}")
    print(f"  {draft.get('body')}")


def cmd_watch(client: BoardApiClient, interval: float) -> None:
    """Prefer WebSocket; fall back to HTTP poll."""

    def render(b: BoardSnapshot) -> None:
        print("\033[2J\033[H", end="")
        print(f"watch · {client.base_url} · rev {b.revision}")
        _print_dash(b)

    try:
        async def runner() -> None:
            await client.watch_ws(render)

        asyncio.run(runner())
    except (RuntimeError, Exception) as e:
        print(f"ws unavailable ({e}); polling every {interval}s", file=sys.stderr)
        last = -1
        try:
            while True:
                try:
                    b = client.get_board()
                    if b.revision != last:
                        last = b.revision
                        render(b)
                except Exception as err:
                    cached = client.cache.load()
                    if cached and cached.revision != last:
                        last = cached.revision
                        render(cached)
                    print(f"poll error: {err}", file=sys.stderr)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nbye")


def cmd_doctor(client: BoardApiClient) -> None:
    print("casual-board debian-client doctor")
    print(f"  base_url  {client.base_url}")
    print(f"  token_set {bool(client.token)}")
    print(f"  cache     {client.cache.path}")
    try:
        h = client.health()
        print(f"  health    OK rev={h.get('revision')} auth={h.get('auth_mode')}")
    except Exception as e:
        print(f"  health    FAIL {e}")
    try:
        b = client.get_board()
        print(f"  board     OK rev={b.revision} status={b.status_label}")
    except Exception as e:
        cached = client.cache.load()
        print(f"  board     FAIL {e}")
        print(f"  cache_lg  {'yes rev='+str(cached.revision) if cached else 'no'}")
    adapter = NullLocalDashboardAdapter()
    print(f"  adapter   {adapter.apply_snapshot(client.cache.load() or BoardSnapshot())['reason']}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="casual-board", description="Debian client for Casual Board")
    p.add_argument("--url", default=None, help="API base URL")
    p.add_argument("--token", default=None, help="Bearer token")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("dash")
    sub.add_parser("sync")
    w = sub.add_parser("watch")
    w.add_argument("--interval", type=float, default=2.0)
    c = sub.add_parser("capture")
    c.add_argument("note", nargs="+")
    sub.add_parser("doctor")

    args = p.parse_args(argv)
    client = BoardApiClient(base_url=args.url, token=args.token)

    if args.cmd == "status":
        cmd_status(client)
    elif args.cmd == "dash":
        cmd_dash(client)
    elif args.cmd == "sync":
        cmd_sync(client)
    elif args.cmd == "watch":
        cmd_watch(client, args.interval)
    elif args.cmd == "capture":
        cmd_capture(client, " ".join(args.note))
    elif args.cmd == "doctor":
        cmd_doctor(client)


if __name__ == "__main__":
    main()
