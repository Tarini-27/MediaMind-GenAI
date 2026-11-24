"""Tests for the LangChain path (get_chat_model / TraceCallback). Skipped where LangChain can't load,
e.g. Windows machines whose Application Control policy blocks its compiled dependencies."""
import json

import pytest

pytest.importorskip("langchain_core", reason="LangChain not loadable on this machine")
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, LLMResult  # noqa: E402

from mediamind.config import get_config  # noqa: E402
from mediamind.llm import MissingApiKey, TraceCallback, get_chat_model  # noqa: E402
from mediamind.runs import BudgetExceeded, run_scope, trace_dir  # noqa: E402


def trace_file(run_id: str) -> dict:
    return json.loads((trace_dir() / f"{run_id}.json").read_text())


def _llm_result(tin=120, tout=30, cost=0.00042, model="openai/gpt-4.1-mini"):
    msg = AIMessage(content="hi", usage_metadata={"input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout},
                    response_metadata={"model_name": model, "token_usage": {"cost": cost}})
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def test_llm_call_records_tokens_cost_latency():
    cb = TraceCallback(agent="answerer")
    with run_scope(user_id="demo", mode="ask") as run:
        cb.on_chat_model_start({}, [], run_id="00000000-0000-0000-0000-000000000001")
        cb.on_llm_end(_llm_result(), run_id="00000000-0000-0000-0000-000000000001")
    t = trace_file(run.run_id)
    llm = [e for e in t["events"] if e["type"] == "llm"][0]
    assert llm["name"] == "openai/gpt-4.1-mini" and llm["tokens_in"] == 120 and llm["cost_usd"] == 0.00042
    assert llm["response"] == "hi"
    assert t["totals"]["cost_usd"] == 0.00042 and t["totals"]["cost_complete"] is True


def test_unknown_cost_is_null_not_guessed():
    cb = TraceCallback()
    with run_scope(user_id="demo", mode="ask") as run:
        cb.on_chat_model_start({}, [], run_id="00000000-0000-0000-0000-000000000002")
        cb.on_llm_end(_llm_result(cost=None), run_id="00000000-0000-0000-0000-000000000002")
    t = trace_file(run.run_id)
    assert t["totals"]["cost_complete"] is False and t["events"][0]["cost_usd"] is None


def test_llm_error_is_traced():
    cb = TraceCallback(model="m")
    with run_scope(user_id="demo", mode="ask") as run:
        cb.on_chat_model_start({}, [], run_id="00000000-0000-0000-0000-000000000003")
        cb.on_llm_error(TimeoutError("provider timed out"), run_id="00000000-0000-0000-0000-000000000003")
    assert "TimeoutError" in trace_file(run.run_id)["events"][0]["error"]


def test_token_budget_stops_next_llm_call(monkeypatch):
    monkeypatch.setattr(get_config().budgets, "max_tokens_per_run", 100)
    cb = TraceCallback()
    with pytest.raises(BudgetExceeded):
        with run_scope(user_id="demo", mode="ask") as run:
            cb.on_chat_model_start({}, [], run_id="00000000-0000-0000-0000-000000000004")
            cb.on_llm_end(_llm_result(tin=90, tout=20), run_id="00000000-0000-0000-0000-000000000004")
            cb.on_chat_model_start({}, [], run_id="00000000-0000-0000-0000-000000000005")
    assert trace_file(run.run_id)["status"] == "budget_exceeded"


def test_get_chat_model_reads_model_from_config_and_needs_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(MissingApiKey):
        get_chat_model("specialist")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    m = get_chat_model("specialist")
    assert m.model_name == get_config().models.specialist and isinstance(m.callbacks[0], TraceCallback)


def test_langchain_call_records_prompt_and_reply():
    from langchain_core.messages import HumanMessage
    cb = TraceCallback(agent="answerer")
    with run_scope(user_id="demo", mode="ask") as run:
        cb.on_chat_model_start({}, [[HumanMessage(content="Which recipes need no oven?")]],
                               run_id="00000000-0000-0000-0000-000000000009")
        cb.on_llm_end(_llm_result(), run_id="00000000-0000-0000-0000-000000000009")
    ev = trace_file(run.run_id)["events"][0]
    assert ev["prompt"] == [{"role": "human", "content": "Which recipes need no oven?"}] and ev["response"] == "hi"
