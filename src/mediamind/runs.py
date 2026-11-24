"""Run tracing: every run gets a run_id and writes one JSON trace file the evaluation harness can read.

    with run_scope(user_id="demo", mode="ask", case_id="dev-007", input={"question": q}) as run:
        ...                       # LLM calls (via the callback in llm.py) and tool calls (via hooks)
        run.output = {...}        #  are recorded into `run` automatically
    # -> data/traces/<run_id>.json

A trace holds: run and case IDs, config name/version/hash and experiment flags, every LLM call
(model, tokens, cost, latency, error), every tool call (agent, tool, outcome, latency), guardrail and
approval events, totals, final status (ok | error | blocked | budget_exceeded | timeout) and output.
Text is scrubbed (PII and secrets) and truncated before it is written. Format: docs/trace_format.md.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from mediamind import metrics
from mediamind.config import ROOT, Config, get_config
from mediamind.control.guardrails import scrub

TRACE_VERSION = "0.1"
STATUSES = ("ok", "error", "blocked", "budget_exceeded", "timeout")


class BudgetExceeded(Exception):
    """Raised when a run goes over its tool-call, token or cost budget."""


def trace_dir(cfg: Config | None = None) -> Path:
    cfg = cfg or get_config()
    d = Path(os.environ.get("MEDIAMIND_TRACES", ROOT / cfg.tracing.dir))
    d.mkdir(parents=True, exist_ok=True)
    return d


_DATA_URI = re.compile(r"data:([\w.+/-]+);base64,([A-Za-z0-9+/=\s]+)")


def _drop_media(text: str) -> str:
    """Images sent to a model are base64 data URIs: keep a short placeholder, never the bytes."""
    return _DATA_URI.sub(lambda m: f"[{m.group(1)}, {len(m.group(2)) * 3 // 4 // 1024} KB]", text)


def _clean(value: Any, limit: int) -> Any:
    """Drop embedded media, scrub PII and secrets, and truncate every string inside a JSON-like value."""
    if isinstance(value, str):
        v = scrub(_drop_media(value))
        return v if len(v) <= limit else v[:limit] + f"…[+{len(v) - limit} chars]"
    if isinstance(value, dict):
        return {str(k): _clean(v, limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, limit) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clean(str(value), limit)


@dataclass
class Run:
    user_id: str
    mode: str
    cfg: Config
    case_id: str | None = None
    input: Any = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
    status: str = "ok"
    error: str | None = None
    output: Any = None
    runner: str = ""
    events: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_complete: bool = True            # False if any LLM call had no cost reported
    _t0: float = field(default_factory=time.perf_counter)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _written: bool = False

    # ---------------------------------------------------------------- recording
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def event(self, type_: str, name: str, **fields: Any) -> dict:
        ev = {"t_ms": self.elapsed_ms(), "type": type_, "name": name, **fields}
        with self._lock:
            self.events.append(ev)
        return ev

    def add_llm(self, *, model: str, tokens_in: int, tokens_out: int, cost_usd: float | None,
                latency_ms: float, error: str | None = None, agent: str | None = None,
                prompt: Any = None, response: Any = None) -> None:
        with self._lock:
            self.llm_calls += 1
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            if cost_usd is None:
                self.cost_complete = False
            else:
                self.cost_usd += cost_usd
        content = {"prompt": prompt, "response": response} if self.cfg.tracing.capture_content else {}
        self.event("llm", model, agent=agent, tokens_in=tokens_in, tokens_out=tokens_out,
                   cost_usd=cost_usd, latency_ms=latency_ms, error=error, **content)
        metrics.LLM_CALLS.labels(model, "error" if error else "ok").inc()
        metrics.TOKENS.labels(model, "in").inc(tokens_in)
        metrics.TOKENS.labels(model, "out").inc(tokens_out)
        if cost_usd:
            metrics.RUN_COST.labels(model).inc(cost_usd)

    def add_tool(self, *, agent: str, tool: str, outcome: str, latency_ms: float,
                 args: Any = None, error: str | None = None) -> None:
        with self._lock:
            self.tool_calls += 1
        self.event("tool", tool, agent=agent, outcome=outcome, latency_ms=latency_ms, args=args, error=error)
        metrics.TOOL_CALLS.labels(tool, outcome).inc()

    # ---------------------------------------------------------------- budget
    def over_budget(self) -> str | None:
        b = self.cfg.budgets
        if self.tool_calls >= b.max_tool_calls_per_run:
            return f"tool-call budget reached ({b.max_tool_calls_per_run})"
        if self.tokens_in + self.tokens_out >= b.max_tokens_per_run:
            return f"token budget reached ({b.max_tokens_per_run})"
        if self.cost_usd >= b.max_cost_usd_per_run:
            return f"cost budget reached (${b.max_cost_usd_per_run})"
        return None

    def check_budget(self) -> None:
        if reason := self.over_budget():
            self.event("budget", "exceeded", reason=reason)
            raise BudgetExceeded(reason)

    # ---------------------------------------------------------------- output
    def to_trace(self) -> dict:
        c = self.cfg
        limit = c.tracing.max_field_chars
        return {
            "trace_version": TRACE_VERSION,
            "run_id": self.run_id, "case_id": self.case_id, "user_id": self.user_id, "mode": self.mode,
            "runner": self.runner,
            "config": {"name": c.name, "version": c.version, "hash": c.hash,
                       "experiment": c.experiment.model_dump(),
                       "models": c.models.model_dump()},
            "started_at": self.started_at, "latency_ms": self.elapsed_ms(),
            "status": self.status, "error": _clean(self.error, limit),
            "totals": {"llm_calls": self.llm_calls, "tool_calls": self.tool_calls,
                       "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                       "cost_usd": round(self.cost_usd, 8), "cost_complete": self.cost_complete},
            "input": _clean(self.input, limit),
            "output": _clean(self.output, limit),
            "events": _clean(self.events, limit),
        }

    def finish(self, status: str | None = None, error: str | None = None) -> Path | None:
        """Write the trace once. Later calls (e.g. a timed-out worker finishing) are ignored."""
        with self._lock:
            if self._written:
                return None
            self._written = True
        if status:
            self.status = status
        if error:
            self.error = error
        path = trace_dir(self.cfg) / f"{self.run_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_trace(), indent=2, ensure_ascii=False, default=str))
        os.replace(tmp, path)                      # atomic: the harness never reads a half-written file
        metrics.RUNS.labels(self.mode, self.status).inc()
        metrics.RUN_SECONDS.labels(self.mode).observe(self.elapsed_ms() / 1000)
        return path


_current: ContextVar[Run | None] = ContextVar("mediamind_run", default=None)


def current_run() -> Run | None:
    return _current.get()


@contextmanager
def run_scope(*, user_id: str, mode: str, case_id: str | None = None, input: Any = None,
              cfg: Config | None = None, run: Run | None = None) -> Iterator[Run]:
    """Open a run, make it current for this thread/task, and always write its trace on exit."""
    run = run or Run(user_id=user_id, mode=mode, cfg=cfg or get_config(), case_id=case_id, input=input)
    token = _current.set(run)
    try:
        yield run
    except BudgetExceeded as e:
        run.finish("budget_exceeded", str(e))
        raise
    except Exception as e:
        run.finish("error", f"{type(e).__name__}: {e}")
        raise
    else:
        run.finish()
    finally:
        _current.reset(token)


def load_trace(run_id: str, cfg: Config | None = None) -> dict | None:
    if not run_id.isalnum():
        return None
    path = trace_dir(cfg) / f"{run_id}.json"
    return json.loads(path.read_text()) if path.exists() else None
