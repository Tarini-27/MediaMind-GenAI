"""Pre/post tool hooks. Wrap EVERY tool call: `call_tool(...)` is the only way agents reach MCP tools.

pre-tool : user_id present + budget (always) + permission and approval (when defences are on)
call     : user_id injected by the hook, never taken from the model
post-tool: log with PII and secrets scrubbed, and record the call in the current run's trace

Budget applies in every configuration: experiments must compare systems with the same resources,
so switching defences off (E2) does not lift it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from mediamind.config import Config
from mediamind.control.guardrails import scrub
from mediamind.runs import current_run

log = logging.getLogger("mediamind.tools")


@dataclass
class ToolError:
    """Structured error: hooks return this instead of raising, so agents can recover."""
    code: str            # permission_denied | budget_exceeded | missing_user | approval_required | tool_error
    message: str

    def dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class RunBudget:
    """Stand-alone call counter for code that runs outside a traced run (tests, scripts)."""
    max_calls: int
    calls: int = 0

    def spend(self) -> bool:
        if self.calls >= self.max_calls:
            return False
        self.calls += 1
        return True


def call_tool(cfg: Config, budget: RunBudget | None = None, *, agent: str, tool: str, user_id: str | None,
              args: dict[str, Any], tool_fn: Callable[..., Any], approved: bool = False) -> Any:
    run = current_run()
    t0 = time.perf_counter()

    def done(outcome: str, result: Any, error: str | None = None) -> Any:
        if run:
            run.add_tool(agent=agent, tool=tool, outcome=outcome, args=args, error=error,
                         latency_ms=round((time.perf_counter() - t0) * 1000, 1))
        log.info("tool=%s agent=%s user=%s outcome=%s args=%s", tool, agent, user_id, outcome, scrub(str(args)))
        return result

    def block(code: str, message: str) -> dict:
        return done(f"blocked:{code}", ToolError(code, message).dict(), message)

    # ---- pre-tool
    if not user_id:
        return block("missing_user", "every tool call needs a user_id")
    if run and (reason := run.over_budget()):
        return block("budget_exceeded", reason)
    if budget and not budget.spend():
        return block("budget_exceeded", f"over {budget.max_calls} calls this run")
    if cfg.experiment.defences:  # E2: with defences off, these checks are skipped
        if tool not in cfg.permissions.get(agent, []):
            return block("permission_denied", f"agent {agent!r} may not call {tool!r}")
        if tool in cfg.write_tools and not approved:
            return block("approval_required", f"{tool!r} needs an approved proposal")

    # ---- call (user_id is injected by the hook, never taken from the model)
    try:
        result = tool_fn(**{**args, "user_id": user_id})
    except Exception as e:  # a crashing tool becomes a structured error the agent can handle
        return done("error", ToolError("tool_error", f"{type(e).__name__}: {e}").dict(), f"{type(e).__name__}: {e}")
    # ---- post-tool
    return done("ok", result)
