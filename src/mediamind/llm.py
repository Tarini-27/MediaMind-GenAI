"""Model access for every agent: models come from the config, and every call is traced and budgeted.

Two ways in, same tracing and budget:

    from mediamind.llm import chat                     # plain HTTPS, no LangChain needed
    reply = chat([{"role": "user", "content": "hi"}], role="specialist", agent="answerer")
    reply["content"]

    from mediamind.llm import get_chat_model           # LangChain chat model, for LangGraph agents
    llm = get_chat_model("specialist")
    llm.invoke(messages)

`chat()` works on machines where Windows Application Control blocks LangChain's compiled
dependencies (xxhash, orjson, zstandard, tiktoken). LangChain is optional: if it can't load,
importing this module still works and get_chat_model() explains why it can't run.

Cost: OpenRouter reports the real cost per call when asked (usage.include), so traces use the
provider's number. If a call reports none, the price table in the config is used; if that is empty
too, the cost is recorded as unknown (null), never guessed.
"""
from __future__ import annotations

import os
import time
from typing import Any
from uuid import UUID

from mediamind.config import Config, get_config
from mediamind.runs import current_run


try:  # optional: blocked on some Windows machines by Application Control
    from langchain_core.callbacks import BaseCallbackHandler
    LANGCHAIN_ERROR: str | None = None
except ImportError as e:  # includes "DLL load failed ... blocked by Application Control policy"
    BaseCallbackHandler = object  # type: ignore[misc,assignment]
    LANGCHAIN_ERROR = f"{type(e).__name__}: {e}"


class MissingApiKey(RuntimeError):
    pass


class LLMUnavailable(RuntimeError):
    pass


def _api_key(cfg: Config) -> str:
    key = os.environ.get(cfg.llm.api_key_env)
    if not key:
        from mediamind.config import ROOT
        env = ROOT / ".env"
        raise MissingApiKey(f"{cfg.llm.api_key_env} is not set. Looked in the environment and in {env} "
                            f"({'exists' if env.exists() else 'NOT FOUND'}). The key is never stored in the config.")
    return key


def _usage(response: Any) -> tuple[int, int, float | None, str | None]:
    """Pull (tokens_in, tokens_out, cost, model) out of a LangChain LLMResult."""
    tin = tout = 0
    cost = None
    model = None
    lo = getattr(response, "llm_output", None) or {}
    model = lo.get("model_name") or lo.get("model")
    tu = lo.get("token_usage") or {}
    for gens in getattr(response, "generations", []) or []:
        for g in gens:
            msg = getattr(g, "message", None)
            um = getattr(msg, "usage_metadata", None) or {}
            tin += um.get("input_tokens", 0)
            tout += um.get("output_tokens", 0)
            rm = getattr(msg, "response_metadata", None) or {}
            model = model or rm.get("model_name")
            c = (rm.get("token_usage") or {}).get("cost")
            if c is not None:
                cost = (cost or 0.0) + float(c)
    if not (tin or tout) and tu:
        tin, tout = tu.get("prompt_tokens", 0), tu.get("completion_tokens", 0)
    if cost is None and tu.get("cost") is not None:
        cost = float(tu["cost"])
    return tin, tout, cost, model


def _messages(messages: Any) -> list[dict]:
    """LangChain messages (list of lists) -> [{"role", "content"}] for the trace."""
    out = []
    for batch in messages or []:
        for m in (batch if isinstance(batch, list) else [batch]):
            out.append({"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", str(m))})
    return out


def _reply_text(response: Any) -> str:
    for gens in getattr(response, "generations", []) or []:
        for g in gens:
            return getattr(g, "text", "") or getattr(getattr(g, "message", None), "content", "")
    return ""


def _price(cfg: Config, model: str | None, tin: int, tout: int) -> float | None:
    p = cfg.llm.pricing.get(model or "")
    if not p:
        return None
    return (tin * p.get("input", 0) + tout * p.get("output", 0)) / 1_000_000


class TraceCallback(BaseCallbackHandler):
    """Records every chat-model call into the current run, and stops a run that is over budget."""
    raise_error = True          # let BudgetExceeded stop the call instead of being swallowed

    def __init__(self, agent: str | None = None, model: str | None = None) -> None:
        self.agent = agent
        self.model = model
        self._starts: dict[UUID, float] = {}
        self._prompts: dict[UUID, list[dict]] = {}

    def on_chat_model_start(self, serialized: dict, messages: Any, *, run_id: UUID, **kw: Any) -> None:
        run = current_run()
        if run:
            run.check_budget()            # pre-call budget check: raises BudgetExceeded
        self._starts[run_id] = time.perf_counter()
        self._prompts[run_id] = _messages(messages)

    on_llm_start = on_chat_model_start   # plain (non-chat) models

    def on_llm_end(self, response: Any, *, run_id: UUID, **kw: Any) -> None:
        run = current_run()
        t0 = self._starts.pop(run_id, time.perf_counter())
        prompt = self._prompts.pop(run_id, None)
        if not run:
            return
        tin, tout, cost, model = _usage(response)
        model = model or self.model or "unknown"
        if cost is None:
            cost = _price(run.cfg, model, tin, tout)
        run.add_llm(model=model, tokens_in=tin, tokens_out=tout, cost_usd=cost,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1), agent=self.agent,
                    prompt=prompt, response=_reply_text(response))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kw: Any) -> None:
        run = current_run()
        t0 = self._starts.pop(run_id, time.perf_counter())
        prompt = self._prompts.pop(run_id, None)
        if run:
            run.add_llm(model=self.model or "unknown", tokens_in=0, tokens_out=0, cost_usd=0.0,
                        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                        error=f"{type(error).__name__}: {error}", agent=self.agent, prompt=prompt)


RETRY_STATUS = {429, 500, 502, 503, 504}


def chat(messages: list[dict], role: str = "specialist", *, agent: str | None = None,
         cfg: Config | None = None, **params: Any) -> dict:
    """One chat completion over plain HTTPS (OpenAI-compatible, OpenRouter by default).

    Traced into the current run and budgeted exactly like get_chat_model(). Returns
    {"content", "model", "tokens_in", "tokens_out", "cost_usd"}. Never logs the key.
    """
    import requests

    cfg = cfg or get_config()
    model = getattr(cfg.models, role)
    key = _api_key(cfg)
    run = current_run()
    if run:
        run.check_budget()
    body = {"model": model, "messages": messages, "temperature": cfg.llm.temperature,
            "usage": {"include": True}, **params}
    t0 = time.perf_counter()
    error: str | None = None
    data: dict = {}
    for attempt in range(cfg.llm.max_retries + 1):
        try:
            r = requests.post(f"{cfg.llm.base_url.rstrip('/')}/chat/completions", json=body, timeout=cfg.llm.timeout_s,
                              headers={"Authorization": f"Bearer {key}", "X-Title": "MediaMind"})
            if r.status_code in RETRY_STATUS and attempt < cfg.llm.max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            if r.status_code >= 400:
                detail = r.text[:300]
                error = f"HTTP {r.status_code}: {detail}"
                break
            data = r.json()
            error = None
            break
        except requests.RequestException as e:
            error = f"{type(e).__name__}: {e}"
            if attempt >= cfg.llm.max_retries:
                break
            time.sleep(min(2 ** attempt, 8))
    latency = round((time.perf_counter() - t0) * 1000, 1)
    if error:
        if run:
            run.add_llm(model=model, tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=latency, error=error,
                        agent=agent, prompt=messages)
        raise LLMUnavailable(error)
    usage = data.get("usage") or {}
    tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    used_model = data.get("model") or model
    cost = usage.get("cost")
    cost = float(cost) if cost is not None else _price(cfg, used_model, tin, tout)
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if run:
        run.add_llm(model=used_model, tokens_in=tin, tokens_out=tout, cost_usd=cost, latency_ms=latency, agent=agent,
                    prompt=messages, response=content)
    return {"content": content, "model": used_model, "tokens_in": tin, "tokens_out": tout, "cost_usd": cost}


def get_chat_model(role: str = "specialist", *, agent: str | None = None, cfg: Config | None = None, **kw: Any):
    """A LangChain chat model for `role` ("supervisor" | "specialist" | "judge"), configured from mediamind.yaml."""
    if LANGCHAIN_ERROR:
        raise LLMUnavailable(f"LangChain can't load on this machine ({LANGCHAIN_ERROR}). Use mediamind.llm.chat(), "
                             "or run the agents in Docker or WSL, where Windows Application Control does not apply.")
    from langchain_openai import ChatOpenAI

    cfg = cfg or get_config()
    model = getattr(cfg.models, role)
    key = _api_key(cfg)
    return ChatOpenAI(
        model=model, base_url=cfg.llm.base_url, api_key=key,
        timeout=cfg.llm.timeout_s, max_retries=cfg.llm.max_retries, temperature=cfg.llm.temperature,
        callbacks=[TraceCallback(agent=agent or role, model=model)],
        extra_body={"usage": {"include": True}},      # ask OpenRouter to report the real cost
        **kw,
    )
