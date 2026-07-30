"""Hermes Graph Recall invocation: HERMES_HOME=... hermes -z <PROMPT>."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("graph_recall_worker.hermes")

HermesRunnerFn = Callable[[str, dict[str, Any]], str]


@dataclass
class HermesResult:
    ok: bool
    raw_text: str
    parsed: dict[str, Any] | None
    error_category: str | None = None
    duration_s: float = 0.0
    command: list[str] | None = None


class InvalidHermesCLIError(ValueError):
    """Raised when argv would not be accepted by the installed Hermes parser."""


def validate_hermes_argv(cmd: list[str]) -> None:
    """Real CLI: hermes -z / --oneshot <PROMPT>. No --toolset, no Hermes --timeout."""
    if not cmd or cmd[0] != "hermes":
        raise InvalidHermesCLIError("command must start with hermes")
    if "--toolset" in cmd:
        raise InvalidHermesCLIError(
            "unsupported flag --toolset (tools come from HERMES_HOME profile)"
        )
    if "--timeout" in cmd:
        raise InvalidHermesCLIError(
            "unsupported flag --timeout (use Python subprocess timeout)"
        )
    if "-z" in cmd:
        i = cmd.index("-z")
        if i + 1 >= len(cmd) or cmd[i + 1].startswith("-"):
            raise InvalidHermesCLIError("-z requires a prompt argument")
    elif "--oneshot" in cmd:
        i = cmd.index("--oneshot")
        if i + 1 >= len(cmd) or cmd[i + 1].startswith("-"):
            raise InvalidHermesCLIError("--oneshot requires a prompt argument")
    else:
        raise InvalidHermesCLIError("missing -z / --oneshot")


def build_hermes_command(prompt: str, *, toolsets: str | None = None) -> list[str]:
    """
    Graph Recall invocation:
      HERMES_HOME=... hermes -z '<structured culinary enquiry>'
    Prompt is an argv element (not stdin). Tools come from the graph-recall profile.
    """
    del toolsets  # unused — profile owns tools
    cmd: list[str] = ["hermes", "-z", prompt]
    validate_hermes_argv(cmd)
    return cmd


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


def validate_graph_recall_output(
    parsed: dict[str, Any] | None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Structural validation of Hermes Graph Recall JSON."""
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
    cleaned_mem = []
    for raw in mem:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        finding = str(raw.get("finding") or raw.get("excerpt") or "").strip()
        cleaned_mem.append(
            {
                "title": title,
                "path": str(raw.get("path") or "").strip(),
                "relevance": str(raw.get("relevance") or "").strip(),
                "finding": finding,
                "excerpt": finding,
            }
        )
    return True, None, {
        "kitchen_memory": cleaned_mem,
        "enrichment": enrichment,
        "meta": parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {},
    }


def run_hermes(
    prompt: str,
    *,
    timeout_s: int,
    env: dict[str, str] | None = None,
    toolsets: str | None = None,
    runner: HermesRunnerFn | None = None,
) -> HermesResult:
    import time

    t0 = time.monotonic()
    try:
        cmd = build_hermes_command(prompt, toolsets=toolsets)
    except InvalidHermesCLIError:
        return HermesResult(
            ok=False,
            raw_text="",
            parsed=None,
            error_category="invalid_cli",
            duration_s=time.monotonic() - t0,
            command=None,
        )

    if runner is not None:
        try:
            text = runner(prompt, {"command": cmd, "timeout_s": timeout_s})
            parsed = extract_json_object(text)
            ok, cat, cleaned = validate_graph_recall_output(parsed)
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
    for k in (
        "CASUAL_BOARD_GRAPH_RECALL_TOKEN",
        "CASUAL_BOARD_TOKEN",
        "CASUAL_BOARD_BRIDGE_TOKEN",
        "CASUAL_BOARD_UI_PASSWORD",
        "CASUAL_BOARD_EVIDENCE_AI_API_KEY",
        "OPENAI_API_KEY",
        "XAI_API_KEY",
    ):
        run_env.pop(k, None)

    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=run_env,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout:
            err = (proc.stderr or "").lower()
            if "unrecognized" in err or "invalid" in err or "usage" in err:
                return HermesResult(
                    ok=False,
                    raw_text="",
                    parsed=None,
                    error_category="invalid_cli",
                    duration_s=time.monotonic() - t0,
                    command=cmd,
                )
            return HermesResult(
                ok=False,
                raw_text="",
                parsed=None,
                error_category="hermes_failure",
                duration_s=time.monotonic() - t0,
                command=cmd,
            )
        parsed = extract_json_object(proc.stdout or "")
        ok, cat, cleaned = validate_graph_recall_output(parsed)
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


def dry_run_hermes_parser(prompt: str = "ping") -> tuple[bool, str]:
    try:
        cmd = build_hermes_command(prompt)
    except InvalidHermesCLIError as e:
        return False, f"argv invalid: {e}"
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        err = ((proc.stderr or "") + (proc.stdout or "")).lower()
        if (
            "unrecognized arguments" in err
            or "invalid option" in err
            or "no such option" in err
        ):
            return False, f"hermes rejected argv: {err[:200]}"
        return True, "hermes accepted argv shape (or ran without arg error)"
    except FileNotFoundError:
        return True, "hermes not installed here; argv validated (hermes -z <prompt>)"
    except subprocess.TimeoutExpired:
        return True, "hermes started (timeout) — no argument error"
    except Exception as e:  # noqa: BLE001
        return False, f"dry_run error: {type(e).__name__}"
