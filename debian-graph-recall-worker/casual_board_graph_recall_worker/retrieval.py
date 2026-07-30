"""Read-only culinary retrieval via logseq-graph recall, then search (shell=False)."""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any, Callable

from . import LOGSEQ_GRAPH_BIN, LOGSEQ_GRAPH_ROOT
from .hermes_runner import filter_kitchen_memory

log = logging.getLogger("graph_recall_worker.retrieval")

RecallRunnerFn = Callable[[list[str]], str]

_SAFE_QUERY = re.compile(r"[^a-zA-Z0-9 ,.\-]")
_MAX_QUERY_LEN = 160


def sanitise_query_fragment(text: str, *, max_len: int = 48) -> str:
    s = (text or "").replace("\x00", " ")
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = _SAFE_QUERY.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    while s.startswith("-"):
        s = s.lstrip("-").strip()
    tokens = [t for t in s.split() if "/" not in t and "\\" not in t]
    s = " ".join(tokens)
    return s[:max_len]


def build_recall_query(payload: dict[str, Any]) -> str:
    c = payload.get("consultation") or {}
    parts: list[str] = []
    for key in ("mode", "title", "desired_outcome", "service_context"):
        frag = sanitise_query_fragment(str(c.get(key) or ""), max_len=32)
        if frag:
            parts.append(frag)
    raw = str(c.get("ingredients_or_problem") or "")
    for tok in re.split(r"[\n,;]+", raw)[:6]:
        frag = sanitise_query_fragment(tok, max_len=24)
        if frag:
            parts.append(frag)
    for lot in (payload.get("produce_lots") or [])[:4]:
        if isinstance(lot, dict):
            frag = sanitise_query_fragment(str(lot.get("name") or ""), max_len=24)
            if frag:
                parts.append(frag)
    for ing in (payload.get("ingredients") or [])[:4]:
        if isinstance(ing, dict):
            frag = sanitise_query_fragment(str(ing.get("name") or ""), max_len=24)
            if frag:
                parts.append(frag)
    q = " ".join(parts).strip()
    q = re.sub(r"\s+", " ", q)[:_MAX_QUERY_LEN]
    return q or "culinary technique stock sauce"


def build_logseq_recall_command(query: str, *, limit: int = 6) -> list[str]:
    limit = max(1, min(int(limit), 6))
    safe_q = sanitise_query_fragment(query, max_len=_MAX_QUERY_LEN) or "culinary"
    return [LOGSEQ_GRAPH_BIN, "recall", safe_q, "--limit", str(limit)]


def build_logseq_search_command(query: str, *, limit: int = 6) -> list[str]:
    """Read-only search fallback when recall is empty."""
    limit = max(1, min(int(limit), 6))
    safe_q = sanitise_query_fragment(query, max_len=_MAX_QUERY_LEN) or "culinary"
    return [LOGSEQ_GRAPH_BIN, "search", safe_q, "--limit", str(limit)]


def parse_recall_output(text: str) -> list[dict[str, str]]:
    text = (text or "").strip()
    if not text:
        return []
    items: list[dict[str, str]] = []
    if text.startswith("["):
        try:
            import json

            data = json.loads(text)
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    items.append(
                        {
                            "title": str(row.get("title") or row.get("name") or "note"),
                            "path": str(row.get("path") or row.get("file") or ""),
                            "relevance": str(row.get("relevance") or row.get("score") or "search"),
                            "finding": str(
                                row.get("excerpt") or row.get("snippet") or row.get("text") or ""
                            )[:500],
                        }
                    )
                return items
        except Exception:  # noqa: BLE001
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            cols = line.split("\t")
        elif " | " in line:
            cols = [c.strip() for c in line.split("|")]
        else:
            cols = [line]
        path = cols[0].strip() if cols else ""
        title = cols[1].strip() if len(cols) > 1 else path.rsplit("/", 1)[-1]
        finding = cols[2].strip() if len(cols) > 2 else ""
        if path or title:
            items.append(
                {
                    "title": title or "note",
                    "path": path,
                    "relevance": "recall",
                    "finding": finding[:500],
                }
            )
    return items[:6]


def _run_cmd(cmd: list[str], *, timeout_s: int, runner: RecallRunnerFn | None) -> str:
    assert cmd[0] == LOGSEQ_GRAPH_BIN
    assert cmd[1] in {"recall", "search"}
    if runner is not None:
        return runner(cmd)
    proc = subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.stdout or ""


def run_logseq_recall(
    payload: dict[str, Any],
    *,
    graph_root: str = LOGSEQ_GRAPH_ROOT,
    timeout_s: int = 30,
    runner: RecallRunnerFn | None = None,
) -> list[dict[str, str]]:
    """Local-first: recall → search fallback. Only approved graph paths kept."""
    query = build_recall_query(payload)
    try:
        out = _run_cmd(build_logseq_recall_command(query, limit=6), timeout_s=timeout_s, runner=runner)
        raw_items = parse_recall_output(out)
        filtered = filter_kitchen_memory(raw_items, graph_root=graph_root)
        if filtered:
            return filtered
        # empty recall → read-only search
        log.info("logseq_recall_empty fallback=search")
        out2 = _run_cmd(build_logseq_search_command(query, limit=6), timeout_s=timeout_s, runner=runner)
        for row in parse_recall_output(out2):
            row["relevance"] = row.get("relevance") or "search"
        return filter_kitchen_memory(parse_recall_output(out2), graph_root=graph_root)
    except FileNotFoundError:
        log.info("logseq_recall_empty category=bin_missing")
        return []
    except subprocess.TimeoutExpired:
        log.info("logseq_recall_empty category=timeout")
        return []
    except Exception:  # noqa: BLE001
        log.info("logseq_recall_empty category=error")
        return []
