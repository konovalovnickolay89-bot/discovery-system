"""Hermes invocation with restricted read-first toolset. No --yolo."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import LOGSEQ_GRAPH_ROOT as DEFAULT_LOGSEQ_ROOT
from . import RESTRICTED_TOOLSET

log = logging.getLogger("graph_recall_worker.hermes")

# Overridable for tests
LOGSEQ_GRAPH_ROOT = DEFAULT_LOGSEQ_ROOT

HermesRunnerFn = Callable[[str, dict[str, Any]], str]


@dataclass
class HermesResult:
    ok: bool
    raw_text: str
    parsed: dict[str, Any] | None
    error_category: str | None = None
    duration_s: float = 0.0
    command: list[str] | None = None


def build_hermes_command(timeout_s: int) -> list[str]:
    return [
        "hermes",
        "-z",
        "--toolset",
        RESTRICTED_TOOLSET,
        "--timeout",
        str(int(timeout_s)),
    ]


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


def validate_logseq_path(path: str, graph_root: str | None = None) -> bool:
    root_s = graph_root if graph_root is not None else LOGSEQ_GRAPH_ROOT
    if not path or not isinstance(path, str):
        return False
    try:
        root = Path(root_s).resolve()
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = root / p
        resolved = p.resolve()
        return str(resolved).startswith(str(root) + os.sep) or str(resolved) == str(root)
    except Exception:  # noqa: BLE001
        return False


def filter_kitchen_memory(
    items: list[Any],
    *,
    graph_root: str | None = None,
) -> list[dict[str, str]]:
    root = graph_root if graph_root is not None else LOGSEQ_GRAPH_ROOT
    out: list[dict[str, str]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        path = str(raw.get("path") or "").strip()
        relevance = str(raw.get("relevance") or "").strip()
        finding = str(raw.get("finding") or raw.get("excerpt") or "").strip()
        if not title or not path:
            continue
        if not validate_logseq_path(path, root):
            continue
        out.append(
            {
                "title": title,
                "path": path,
                "relevance": relevance,
                "excerpt": finding,
                "finding": finding,
            }
        )
    return out


def validate_hermes_output(parsed: dict[str, Any] | None) -> tuple[bool, str | None, dict[str, Any]]:
    if not parsed or not isinstance(parsed, dict):
        return False, "malformed_json", {}
    mem = parsed.get("kitchen_memory")
    if mem is None:
        mem = []
    if not isinstance(mem, list):
        return False, "malformed_kitchen_memory", {}
    enrichment = parsed.get("enrichment")
    if enrichment is None:
        enrichment = {}
    if not isinstance(enrichment, dict):
        return False, "malformed_enrichment", {}
    opts = enrichment.get("options")
    if isinstance(opts, list) and len(opts) > 3:
        enrichment = {**enrichment, "options": opts[:3]}
    filtered = filter_kitchen_memory(mem, graph_root=LOGSEQ_GRAPH_ROOT)
    return True, None, {
        "kitchen_memory": filtered,
        "enrichment": enrichment,
        "meta": parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {},
    }


def run_hermes(
    prompt: str,
    *,
    timeout_s: int,
    env: dict[str, str] | None = None,
    runner: HermesRunnerFn | None = None,
) -> HermesResult:
    import time

    cmd = build_hermes_command(timeout_s)
    t0 = time.monotonic()
    if runner is not None:
        try:
            text = runner(prompt, {"command": cmd, "timeout_s": timeout_s})
            parsed = extract_json_object(text)
            ok, cat, cleaned = validate_hermes_output(parsed)
            return HermesResult(
                ok=ok,
                raw_text=text,
                parsed=cleaned if ok else None,
                error_category=None if ok else (cat or "malformed_output"),
                duration_s=time.monotonic() - t0,
                command=cmd,
            )
        except TimeoutError:
            return HermesResult(
                ok=False,
                raw_text="",
                parsed=None,
                error_category="timeout",
                duration_s=time.monotonic() - t0,
                command=cmd,
            )
        except Exception:  # noqa: BLE001
            return HermesResult(
                ok=False,
                raw_text="",
                parsed=None,
                error_category="hermes_failure",
                duration_s=time.monotonic() - t0,
                command=cmd,
            )

    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    for k in list(run_env):
        if k in {
            "CASUAL_BOARD_GRAPH_RECALL_TOKEN",
            "CASUAL_BOARD_TOKEN",
            "CASUAL_BOARD_BRIDGE_TOKEN",
            "CASUAL_BOARD_UI_PASSWORD",
        }:
            run_env.pop(k, None)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            env=run_env,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout:
            return HermesResult(
                ok=False,
                raw_text="",
                parsed=None,
                error_category="hermes_failure",
                duration_s=time.monotonic() - t0,
                command=cmd,
            )
        parsed = extract_json_object(proc.stdout or "")
        ok, cat, cleaned = validate_hermes_output(parsed)
        return HermesResult(
            ok=ok,
            raw_text=proc.stdout or "",
            parsed=cleaned if ok else None,
            error_category=None if ok else (cat or "malformed_output"),
            duration_s=time.monotonic() - t0,
            command=cmd,
        )
    except subprocess.TimeoutExpired:
        return HermesResult(
            ok=False,
            raw_text="",
            parsed=None,
            error_category="timeout",
            duration_s=time.monotonic() - t0,
            command=cmd,
        )
    except FileNotFoundError:
        return HermesResult(
            ok=False,
            raw_text="",
            parsed=None,
            error_category="hermes_missing",
            duration_s=time.monotonic() - t0,
            command=cmd,
        )
    except Exception:  # noqa: BLE001
        return HermesResult(
            ok=False,
            raw_text="",
            parsed=None,
            error_category="hermes_failure",
            duration_s=time.monotonic() - t0,
            command=cmd,
        )
