"""Runner registry: what actually executes a run. The API and the evaluation harness call `execute_run`;
which runner handles it is chosen by `experiment.agent_mode` in the config.

Role 3 plugs the LangGraph graph in without touching the API:

    from mediamind.runners import register

    @register("team")                       # also "c0_workflow", "c1_single_agent"
    def run_team(run, request):             # run: mediamind.runs.Run, request: dict
        result = graph.invoke(..., config={"configurable": {"thread_id": run.run_id}})
        return {"answer": ..., "citations": [...], "records": [...], "blocked": None}

Until a runner is registered for the configured mode, the "stub" runner answers (keyword search),
and the trace says runner="stub", so nobody mistakes stub results for agent results.
"""
from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable

from mediamind import metrics
from mediamind.api import store
from mediamind.config import get_config
from mediamind.control.guardrails import check_citations, detect_injection, mask_pii
from mediamind.runs import Run, run_scope

Runner = Callable[[Run, dict], Any]
RUNNERS: dict[str, Runner] = {}
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mm-run")


def register(name: str) -> Callable[[Runner], Runner]:
    def deco(fn: Runner) -> Runner:
        RUNNERS[name] = fn
        return fn
    return deco


def get_runner(agent_mode: str) -> tuple[str, Runner]:
    if agent_mode in RUNNERS:
        return agent_mode, RUNNERS[agent_mode]
    return "stub", RUNNERS["stub"]


@register("stub")
def stub_runner(run: Run, request: dict) -> dict:
    """Keyword-search answer with the real guardrails around it. Replaced by Role 3's graph."""
    if run.mode != "ask":
        raise NotImplementedError(f"mode {run.mode!r} needs the agent graph (Role 3); the stub only answers 'ask'")
    cfg = run.cfg
    q = request.get("question") or ""
    if cfg.experiment.defences and (scan := detect_injection(q)).flagged:
        metrics.BLOCKS.labels("input_injection").inc()
        run.event("guardrail", "input_injection", blocked=True, reason=scan.reason)
        run.status = "blocked"
        return {"answer": "That looks like an instruction aimed at the assistant, so I ignored it.",
                "citations": [], "records": [], "blocked": scan.reason}
    hits = store.search(run.user_id, mask_pii(q))
    run.event("retrieval", "store.search", hits=[h["id"] for h in hits])
    cited = [h["id"] for h in hits]
    if cfg.experiment.defences:
        bad = check_citations(cited, run.user_id, store.get_item)
        run.event("guardrail", "output_citations", blocked=bool(bad), violations=bad)
        if bad:
            metrics.BLOCKS.labels("output_citation").inc()
            run.status = "blocked"
            return {"answer": "I couldn't verify my sources, so I'm not answering.", "citations": [],
                    "records": [], "blocked": "citation check failed"}
    answer = (f"Found {len(hits)} match(es) in your saves." if hits
              else "Nothing in your collections matches that.")          # abstain when empty
    return {"answer": answer, "citations": cited, "records": hits, "blocked": None}


def execute_run(*, user_id: str, mode: str, request: dict, case_id: str | None = None) -> Run:
    """Run one request end to end with a time limit. Always returns the Run; its trace is always written."""
    cfg = get_config()
    run = Run(user_id=user_id, mode=mode, cfg=cfg, case_id=case_id, input=request)
    run.runner, fn = get_runner(cfg.experiment.agent_mode)

    def work() -> None:
        with run_scope(user_id=user_id, mode=mode, run=run):
            run.output = fn(run, request)

    future = _POOL.submit(contextvars.copy_context().run, work)
    try:
        future.result(timeout=cfg.budgets.max_seconds_per_run)
    except FutureTimeout:
        run.finish("timeout", f"run exceeded {cfg.budgets.max_seconds_per_run} s")
    except Exception:
        pass                      # status and error were already recorded by run_scope
    return run
