"""CLI: python -m casual_board_graph_recall_worker run|once|verify-cli

Graph Recall via: HERMES_HOME=... hermes -z <prompt>
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys

from .client import GraphRecallClient
from .hermes_runner import dry_run_hermes_parser
from .worker import GraphRecallWorker

# Hermes user install path first (systemd units should also set PATH)
DEFAULT_PATH = (
    "/home/discovery-system/.local/bin:/usr/local/bin:/usr/bin:/bin"
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            for key in (
                "CASUAL_BOARD_GRAPH_RECALL_TOKEN",
                "CASUAL_BOARD_TOKEN",
                "CASUAL_BOARD_BRIDGE_TOKEN",
                "Bearer ",
            ):
                if key in msg and key.startswith("CASUAL"):
                    return False
            return True

    logging.getLogger().addFilter(_Filter())


def _default_worker_id() -> str:
    host = socket.gethostname().split(".")[0] or "debian"
    return f"graph-recall@{host}"


def ensure_hermes_path() -> None:
    """Prefer discovery-system local bin so user service finds hermes."""
    path = os.environ.get("PATH", "")
    parts = [p for p in path.split(":") if p]
    for p in DEFAULT_PATH.split(":"):
        if p not in parts:
            parts.insert(0, p)
    # Keep preferred order: DEFAULT_PATH then rest
    preferred = DEFAULT_PATH.split(":")
    rest = [p for p in parts if p not in preferred]
    os.environ["PATH"] = ":".join(preferred + rest)


def build_worker(
    *,
    url: str,
    token: str,
    worker_id: str,
    hermes_timeout_s: int,
    home: str,
    hermes_home: str,
    hermes_runner=None,
    client: GraphRecallClient | None = None,
) -> GraphRecallWorker:
    """Construct GraphRecallWorker — only kwargs accepted by current constructor."""
    c = client or GraphRecallClient(url, token, worker_id)
    return GraphRecallWorker(
        c,
        hermes_timeout_s=hermes_timeout_s,
        home=home,
        hermes_home=hermes_home,
        hermes_runner=hermes_runner,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="casual_board_graph_recall_worker")
    p.add_argument(
        "--url",
        default=os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090"),
    )
    p.add_argument(
        "--token",
        default=os.environ.get("CASUAL_BOARD_GRAPH_RECALL_TOKEN", ""),
    )
    p.add_argument(
        "--worker-id",
        default=os.environ.get("CASUAL_BOARD_GRAPH_RECALL_WORKER_ID", ""),
    )
    p.add_argument(
        "--hermes-timeout",
        type=int,
        default=int(os.environ.get("CASUAL_BOARD_GRAPH_RECALL_HERMES_TIMEOUT_S", "240")),
    )
    p.add_argument("--home", default=os.environ.get("HOME", "/home/discovery-system"))
    p.add_argument(
        "--hermes-home",
        default=os.environ.get(
            "HERMES_HOME",
            "/home/discovery-system/.hermes/profiles/graph-recall",
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("once")
    sub.add_parser("verify-cli")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    ensure_hermes_path()
    args = parse_args(argv)

    if args.cmd == "verify-cli":
        ok, msg = dry_run_hermes_parser("ping")
        print(msg)
        sys.exit(0 if ok else 1)

    if "apidiscoverysolution.uk" in args.url or "grok.me" in args.url:
        print("refusing public URL — use http://127.0.0.1:8090", file=sys.stderr)
        sys.exit(2)
    if not args.url.startswith("http://127.0.0.1") and not args.url.startswith(
        "http://localhost"
    ):
        print("refusing non-loopback API URL", file=sys.stderr)
        sys.exit(2)
    if not args.token:
        print("CASUAL_BOARD_GRAPH_RECALL_TOKEN required", file=sys.stderr)
        sys.exit(2)

    ok, msg = dry_run_hermes_parser("ping")
    if not ok:
        print(f"hermes CLI preflight failed: {msg}", file=sys.stderr)
        sys.exit(2)
    logging.getLogger("graph_recall_worker").info("hermes_preflight ok")

    worker_id = args.worker_id or _default_worker_id()
    lease_ttl = int(os.environ.get("CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S", "300"))
    hermes_timeout = min(args.hermes_timeout, max(30, lease_ttl - 30))

    worker = build_worker(
        url=args.url,
        token=args.token,
        worker_id=worker_id,
        hermes_timeout_s=hermes_timeout,
        home=args.home,
        hermes_home=args.hermes_home,
    )
    if args.cmd == "once":
        res = worker.once()
        if res:
            print(
                f"ok consultation_id={res.get('id')} task_status={res.get('task_status')} "
                f"graph_recall_status={res.get('graph_recall_status')}"
            )
        else:
            print("no_job")
        return
    worker.run_loop()


if __name__ == "__main__":
    main()
