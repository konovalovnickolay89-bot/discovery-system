"""CLI: python -m casual_board_graph_recall_worker run|once"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys

from .client import GraphRecallClient
from .worker import GraphRecallWorker


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    # Redact accidental token dumps
    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            for key in (
                "CASUAL_BOARD_GRAPH_RECALL_TOKEN",
                "CASUAL_BOARD_TOKEN",
                "CASUAL_BOARD_BRIDGE_TOKEN",
                "Bearer ",
            ):
                if key in msg and key != "Bearer ":
                    return False
            if "Bearer " in msg and len(msg) > 40:
                record.msg = record.msg.replace(msg, "[redacted]")
            return True

    logging.getLogger().addFilter(_Filter())


def _default_worker_id() -> str:
    host = socket.gethostname().split(".")[0] or "debian"
    return f"graph-recall@{host}"


def main(argv: list[str] | None = None) -> None:
    _configure_logging()
    p = argparse.ArgumentParser(prog="casual_board_graph_recall_worker")
    p.add_argument(
        "--url",
        default=os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090"),
        help="Local API only (default loopback)",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("CASUAL_BOARD_GRAPH_RECALL_TOKEN", ""),
        help="Server-only Graph Recall token",
    )
    p.add_argument("--worker-id", default=os.environ.get("CASUAL_BOARD_GRAPH_RECALL_WORKER_ID", ""))
    p.add_argument(
        "--hermes-timeout",
        type=int,
        default=int(os.environ.get("CASUAL_BOARD_GRAPH_RECALL_HERMES_TIMEOUT_S", "240")),
    )
    p.add_argument(
        "--home",
        default=os.environ.get("HOME", "/home/discovery-system"),
    )
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
    args = p.parse_args(argv)

    if "apidiscoverysolution.uk" in args.url or "grok.me" in args.url:
        print("refusing public URL — use http://127.0.0.1:8090", file=sys.stderr)
        sys.exit(2)
    if not args.url.startswith("http://127.0.0.1") and not args.url.startswith("http://localhost"):
        print("refusing non-loopback API URL", file=sys.stderr)
        sys.exit(2)
    if not args.token:
        print("CASUAL_BOARD_GRAPH_RECALL_TOKEN required", file=sys.stderr)
        sys.exit(2)

    worker_id = args.worker_id or _default_worker_id()
    # Hermes timeout must be safely below lease TTL (default lease 300)
    lease_ttl = int(os.environ.get("CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S", "300"))
    hermes_timeout = min(args.hermes_timeout, max(30, lease_ttl - 30))

    client = GraphRecallClient(args.url, args.token, worker_id)
    worker = GraphRecallWorker(
        client,
        hermes_timeout_s=hermes_timeout,
        home=args.home,
        hermes_home=args.hermes_home,
    )
    if args.cmd == "once":
        res = worker.once()
        # Do not print secrets or full payloads
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
