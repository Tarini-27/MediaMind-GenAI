"""chat(): OpenRouter over plain HTTPS, no LangChain. Traced and budgeted like the LangChain path."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mediamind import llm
from mediamind.config import get_config
from mediamind.runs import BudgetExceeded, run_scope, trace_dir

OK = {"model": "openai/gpt-4.1-mini", "choices": [{"message": {"role": "assistant", "content": "ready"}}],
      "usage": {"prompt_tokens": 12, "completion_tokens": 1, "cost": 0.0000031}}


class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-" + "k" * 40)


def trace(run):
    return json.loads((trace_dir() / f"{run.run_id}.json").read_text())


def test_chat_records_tokens_cost_and_asks_for_cost(monkeypatch):
    sent = {}

    def post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return Resp(200, OK)
    monkeypatch.setattr("requests.post", post)
    with run_scope(user_id="demo", mode="ask") as run:
        out = llm.chat([{"role": "user", "content": "hi"}], agent="answerer")
    assert out["content"] == "ready" and out["cost_usd"] == 0.0000031
    assert sent["url"].endswith("/chat/completions") and sent["body"]["usage"] == {"include": True}
    assert sent["body"]["model"] == get_config().models.specialist
    t = trace(run)
    ev = t["events"][0]
    assert ev["type"] == "llm" and ev["agent"] == "answerer" and ev["tokens_in"] == 12
    assert "kkkkkkkk" not in json.dumps(t)


def test_chat_retries_then_succeeds(monkeypatch):
    calls = iter([Resp(503, text="busy"), Resp(200, OK)])
    monkeypatch.setattr("requests.post", lambda *a, **k: next(calls))
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert llm.chat([{"role": "user", "content": "hi"}])["content"] == "ready"


def test_chat_error_is_traced_and_raised(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(401, text='{"error":"invalid key"}'))
    with pytest.raises(llm.LLMUnavailable, match="401"):
        with run_scope(user_id="demo", mode="ask") as run:
            llm.chat([{"role": "user", "content": "hi"}])
    assert "401" in trace(run)["events"][0]["error"]


def test_chat_respects_budget(monkeypatch):
    monkeypatch.setattr(get_config().budgets, "max_cost_usd_per_run", 0.000001)
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    with pytest.raises(BudgetExceeded):
        with run_scope(user_id="demo", mode="ask"):
            llm.chat([{"role": "user", "content": "hi"}])
            llm.chat([{"role": "user", "content": "again"}])


def test_missing_key_says_where_it_looked(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(llm.MissingApiKey, match=r"\.env"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_works_when_langchain_is_blocked():
    """Simulate Windows Application Control blocking LangChain: the API, runs and chat() still import."""
    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def fake(name, *a, **k):\n"
        "    if name.startswith(('langchain', 'xxhash', 'langsmith')):\n"
        "        raise ImportError('DLL load failed while importing _xxhash: An Application Control policy has blocked this file.')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = fake\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "import mediamind.llm as l, mediamind.api.main\n"
        "assert l.LANGCHAIN_ERROR and 'Application Control' in l.LANGCHAIN_ERROR\n"
        "try:\n"
        "    l.get_chat_model('specialist')\n"
        "except l.LLMUnavailable as e:\n"
        "    assert 'chat()' in str(e)\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr


def test_prompt_and_reply_are_in_the_trace_scrubbed(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    secret = "sk-or-v1-" + "z" * 40
    with run_scope(user_id="demo", mode="ask") as run:
        llm.chat([{"role": "system", "content": "You are the Answerer."},
                  {"role": "user", "content": f"mail me@example.com, key {secret}"}], agent="answerer")
    ev = trace(run)["events"][0]
    assert ev["response"] == "ready" and ev["prompt"][0] == {"role": "system", "content": "You are the Answerer."}
    raw = json.dumps(ev)
    assert secret not in raw and "me@example.com" not in raw and "[SECRET]" in raw


def test_long_prompts_are_truncated(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    with run_scope(user_id="demo", mode="ask") as run:
        llm.chat([{"role": "user", "content": "x" * 10000}])
    content = trace(run)["events"][0]["prompt"][0]["content"]
    assert len(content) < 2100 and "chars]" in content


def test_content_capture_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(get_config().tracing, "capture_content", False)
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    with run_scope(user_id="demo", mode="ask") as run:
        llm.chat([{"role": "user", "content": "private question"}])
    ev = trace(run)["events"][0]
    assert "prompt" not in ev and "response" not in ev and ev["tokens_in"] == 12


def test_prompt_and_reply_are_in_the_trace_scrubbed(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    secret = "sk-or-v1-" + "z" * 40
    with run_scope(user_id="demo", mode="ask") as run:
        llm.chat([{"role": "user", "content": f"hi, my key is {secret}, mail me@x.com"}])
    ev = trace(run)["events"][0]
    assert ev["response"] == "ready" and ev["prompt"][0]["role"] == "user"
    raw = json.dumps(ev)
    assert secret not in raw and "me@x.com" not in raw and "[SECRET]" in raw


def test_content_capture_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(get_config().tracing, "capture_content", False)
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp(200, OK))
    with run_scope(user_id="demo", mode="ask") as run:
        llm.chat([{"role": "user", "content": "hi"}])
    ev = trace(run)["events"][0]
    assert "prompt" not in ev and "response" not in ev and ev["tokens_in"] == 12
