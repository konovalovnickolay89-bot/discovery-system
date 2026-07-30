"""Process one Graph Recall lease: logseq-graph recall → Hermes synthesis → signed result."""

from __future__ import annotations

import logging
import time
from typing import Any

from .client import GraphRecallClient
from .hermes_runner import HermesRunnerFn, run_hermes
from .prompt import build_prompt
from .retrieval import RecallRunnerFn, run_logseq_recall

log = logging.getLogger("graph_recall_worker")


def _safe_log(consultation_id: str, mode: str, **fields: Any) -> None:
    parts = [f"consultation_id={consultation_id}", f"mode={mode}"]
    for k, v in fields.items():
        if k.lower() in {"token", "password", "secret", "prompt", "authorization", "bearer"}:
            continue
        parts.append(f"{k}={v}")
    log.info(" ".join(parts))


class GraphRecallWorker:
    def __init__(
        self,
        client: GraphRecallClient,
        *,
        hermes_timeout_s: int = 240,
        lease_poll_s: float = 25.0,
        hermes_runner: HermesRunnerFn | None = None,
        recall_runner: RecallRunnerFn | None = None,
        home: str = "/home/discovery-system",
        hermes_home: str = "/home/discovery-system/.hermes/profiles/graph-recall",
        hermes_toolsets: str = "",
        graph_root: str = "/home/discovery-system/Logseq/graph",
    ) -> None:
        self.client = client
        self.hermes_timeout_s = hermes_timeout_s
        self.lease_poll_s = lease_poll_s
        self.hermes_runner = hermes_runner
        self.recall_runner = recall_runner
        self.home = home
        self.hermes_home = hermes_home
        self.hermes_toolsets = hermes_toolsets
        self.graph_root = graph_root

    def process_job(self, job: dict[str, Any]) -> dict[str, Any]:
        cid = str(job.get("consultation_id") or "")
        nonce = str(job.get("lease_nonce") or "")
        payload = job.get("payload") or {}
        consultation = payload.get("consultation") or {}
        mode = str(consultation.get("mode") or "build")
        t0 = time.monotonic()
        _safe_log(cid, mode, state="leased", job_id=job.get("id"))

        lease_ttl = float(job.get("lease_ttl_s") or 300)
        lease_deadline = t0 + max(30.0, lease_ttl - 15.0)

        # 1) Worker-owned read-only retrieval (not Hermes tools)
        retrieved = run_logseq_recall(
            payload,
            graph_root=self.graph_root,
            timeout_s=30,
            runner=self.recall_runner,
        )
        _safe_log(cid, mode, state="retrieved", n=len(retrieved))

        prompt = build_prompt(payload, retrieved_context=retrieved)

        attempts = 0
        last_cat = "hermes_failure"
        while attempts < 2 and time.monotonic() < lease_deadline:
            attempts += 1
            remaining = max(10, int(lease_deadline - time.monotonic()))
            timeout = min(self.hermes_timeout_s, remaining)
            result = run_hermes(
                prompt,
                timeout_s=timeout,
                env={
                    "HOME": self.home,
                    "HERMES_HOME": self.hermes_home,
                },
                toolsets=self.hermes_toolsets,
                runner=self.hermes_runner,
            )
            if result.command is None and result.error_category == "invalid_cli":
                last_cat = "invalid_cli"
                break
            if result.command:
                # Enforce real CLI shape
                if "--toolset" in result.command or "--timeout" in result.command:
                    last_cat = "invalid_cli"
                    break
                if "-z" not in result.command and "--oneshot" not in result.command:
                    last_cat = "invalid_cli"
                    break
                # No terminal/file toolsets
                if "--toolsets" in result.command:
                    i = result.command.index("--toolsets")
                    tools = (result.command[i + 1] if i + 1 < len(result.command) else "").lower()
                    if any(b in tools for b in ("terminal", "shell", "file", "filesystem")):
                        last_cat = "toolset_not_restricted"
                        break
            if result.ok and result.parsed:
                # Prefer retrieved-backed memory; merge Hermes synthesis findings for same paths
                mem = result.parsed.get("kitchen_memory") or []
                if not mem and retrieved:
                    mem = [
                        {
                            "title": m.get("title"),
                            "path": m.get("path"),
                            "relevance": m.get("relevance"),
                            "excerpt": m.get("finding") or m.get("excerpt") or "",
                        }
                        for m in retrieved
                    ]
                else:
                    mem = [
                        {
                            "title": m.get("title"),
                            "path": m.get("path"),
                            "relevance": m.get("relevance"),
                            "excerpt": m.get("finding") or m.get("excerpt") or "",
                        }
                        for m in mem
                    ]
                duration = time.monotonic() - t0
                _safe_log(
                    cid,
                    mode,
                    state="completed",
                    duration_s=round(duration, 2),
                    mem_n=len(mem),
                )
                return self.client.post_result(
                    consultation_id=cid,
                    lease_nonce=nonce,
                    status="completed",
                    kitchen_memory=mem,
                    enrichment=result.parsed.get("enrichment") or {},
                    message="kitchen memory returned",
                    proposed_guest_service=False,
                )
            last_cat = result.error_category or "hermes_failure"
            if last_cat in {"timeout", "invalid_cli"}:
                break
            if time.monotonic() >= lease_deadline:
                break

        duration = time.monotonic() - t0
        _safe_log(cid, mode, state="failed", duration_s=round(duration, 2), category=last_cat)
        try:
            return self.client.post_result(
                consultation_id=cid,
                lease_nonce=nonce,
                status="failed",
                kitchen_memory=[],
                enrichment={},
                message=f"Kitchen memory unavailable ({last_cat})",
            )
        except Exception as e:  # noqa: BLE001
            _safe_log(cid, mode, state="result_post_failed", category=type(e).__name__)
            raise

    def once(self) -> dict[str, Any] | None:
        job = self.client.lease(timeout_s=self.lease_poll_s)
        if not job:
            _safe_log("-", "-", state="no_job")
            return None
        return self.process_job(job)

    def run_loop(self) -> None:
        _safe_log("-", "-", state="worker_start", worker_id=self.client.worker_id)
        while True:
            try:
                self.once()
            except Exception as e:  # noqa: BLE001
                log.error("worker_loop_error category=%s", type(e).__name__)
                time.sleep(2.0)
