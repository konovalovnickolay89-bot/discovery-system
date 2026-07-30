"""Real main construction path — constructor kwargs must stay compatible."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from casual_board_graph_recall_worker.main import (
    DEFAULT_PATH,
    build_worker,
    ensure_hermes_path,
    parse_args,
)
from casual_board_graph_recall_worker.worker import GraphRecallWorker


def test_parse_args_has_no_obsolete_flags():
    # global options before subcommand (argparse order)
    args = parse_args(
        ["--token", "t", "--url", "http://127.0.0.1:8090", "once"]
    )
    assert args.cmd == "once"
    assert args.token == "t"
    assert not hasattr(args, "hermes_toolsets")
    assert not hasattr(args, "graph_root")
    with pytest.raises(SystemExit):
        parse_args(["--hermes-toolsets", "x", "once"])
    with pytest.raises(SystemExit):
        parse_args(["--graph-root", "/tmp", "once"])


def test_build_worker_matches_constructor_signature():
    """If GraphRecallWorker.__init__ drops params, main build_worker must still construct."""
    sig = inspect.signature(GraphRecallWorker.__init__)
    params = set(sig.parameters) - {"self"}
    assert "hermes_toolsets" not in params
    assert "graph_root" not in params
    assert "client" in params
    assert "hermes_home" in params

    class FakeClient:
        worker_id = "graph-recall@test"

        def lease(self, timeout_s: float = 25.0):
            return None

        def post_result(self, **kwargs):
            return {}

    w = build_worker(
        url="http://127.0.0.1:8090",
        token="tok",
        worker_id="graph-recall@test",
        hermes_timeout_s=60,
        home="/home/discovery-system",
        hermes_home="/home/discovery-system/.hermes/profiles/graph-recall",
        client=FakeClient(),  # type: ignore[arg-type]
        hermes_runner=lambda prompt, meta: json.dumps(
            {"kitchen_memory": [], "enrichment": {}, "meta": {}}
        ),
    )
    assert isinstance(w, GraphRecallWorker)
    assert w.once() is None


def test_main_once_construction_path_with_fake_client(monkeypatch):
    """Exercise build_worker the same way main does for `once`."""
    called = {}

    class FakeClient:
        worker_id = "graph-recall@test"

        def __init__(self, url, token, worker_id):
            called["client"] = (url, token, worker_id)
            self.worker_id = worker_id

        def lease(self, timeout_s: float = 25.0):
            called["lease"] = True
            return None

        def post_result(self, **kwargs):
            raise AssertionError("no result expected")

    monkeypatch.setattr(
        "casual_board_graph_recall_worker.main.GraphRecallClient",
        FakeClient,
    )

    w = build_worker(
        url="http://127.0.0.1:8090",
        token="secret-token",
        worker_id="graph-recall@debian-minimal",
        hermes_timeout_s=120,
        home="/home/discovery-system",
        hermes_home="/home/discovery-system/.hermes/profiles/graph-recall",
        hermes_runner=lambda p, m: "{}",
    )
    assert w.once() is None
    assert called.get("lease") is True
    assert called["client"][0] == "http://127.0.0.1:8090"
    assert called["client"][2] == "graph-recall@debian-minimal"


def test_ensure_hermes_path_prefers_local_bin(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    ensure_hermes_path()
    path = __import__("os").environ["PATH"]
    assert path.startswith("/home/discovery-system/.local/bin")
    for p in DEFAULT_PATH.split(":"):
        assert p in path.split(":")


def test_main_py_source_has_no_obsolete_kwargs():
    src = (
        Path(__file__).resolve().parents[1]
        / "casual_board_graph_recall_worker"
        / "main.py"
    )
    text = src.read_text()
    assert "hermes_toolsets=" not in text
    assert "graph_root=" not in text
    assert "CASUAL_BOARD_HERMES_TOOLSETS" not in text
    assert "CASUAL_BOARD_LOGSEQ_GRAPH_ROOT" not in text
    assert "LOGSEQ" not in text
