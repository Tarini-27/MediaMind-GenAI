# Trace format (proposed v0.1)

**Status: proposal from Role 4 for Role 1 to accept or change.** Role 1 owns the agreed format (Day 3).
If fields change, bump `trace_version` in `src/mediamind/runs.py` and update this page.

## Where traces are
- One JSON file per run: `data/traces/<run_id>.json` (git-ignored). Written atomically, so a reader never sees a half-written file.
- Also over HTTP, owner-only: `GET /runs/{run_id}?user_id=...`
- Every run is traced: harness runs (`POST /runs`), UI questions (`POST /ask`) and approvals.

## How the harness runs a case
```
POST /runs
{"user_id": "demo", "case_id": "dev-007", "mode": "ask", "question": "Which saved recipes need no oven?"}
→ {"run_id": "...", "case_id": "dev-007", "status": "ok", "runner": "stub", "output": {...},
   "error": null, "latency_ms": 12.4, "totals": {...}, "trace": "/runs/<run_id>"}
```
The experiment is chosen by the config the API was started with (`MEDIAMIND_CONFIG=config/experiments/<name>.yaml`),
never by the request, so one process = one configuration. The trace records which one.

## Top-level fields

| Field | Meaning |
|---|---|
| `trace_version` | Format version, currently `"0.1"` |
| `run_id` | Unique per run |
| `case_id` | The harness's case ID (null for UI runs) |
| `user_id`, `mode` | Who, and what kind of run (`ask`, `approve`, later `save`) |
| `runner` | What executed it: `stub` until Role 3 registers `team` / `c0_workflow` / `c1_single_agent` |
| `config` | `name`, `version`, `hash` (exact settings), `experiment` flags, `models` |
| `started_at`, `latency_ms` | UTC start time and wall-clock duration |
| `status` | `ok` · `blocked` (a guardrail refused) · `error` · `budget_exceeded` · `timeout` |
| `error` | Error text, or null |
| `totals` | `llm_calls`, `tool_calls`, `tokens_in`, `tokens_out`, `cost_usd`, `cost_complete` |
| `input`, `output` | The request and the final result (for `ask`: `answer`, `citations`, `records`, `blocked`) |
| `events` | Every step, in order (below) |

`cost_complete: false` means at least one model call reported no cost, so `cost_usd` is a lower bound. Costs are never guessed.

## Event types (each has `t_ms` since start, `type`, `name`)

| type | name | extra fields |
|---|---|---|
| `llm` | model ID | `agent`, `tokens_in`, `tokens_out`, `cost_usd` (null = unknown), `latency_ms`, `error`, `prompt` (list of `{role, content}`), `response` (text) |
| `tool` | tool name | `agent`, `outcome` (`ok`, `error`, `blocked:<reason>`), `latency_ms`, `args`, `error` |
| `guardrail` | which check | `blocked`, `reason` / `violations` |
| `retrieval` | which search | `hits` (record IDs) |
| `approval` | `approved` / `executed` | `proposal_id`, `hash`, `record_id` |
| `budget` | `exceeded` | `reason` |

Role 3 can add event types (for example `plan`, `replan`, `handoff`) with `run.event(...)`. New types don't break readers.

## Safety of traces
Prompts and replies are recorded when `tracing.capture_content` is true (the default); set it to false to keep only the numbers. All text is passed through the scrubber before writing: emails, phone numbers, card and Aadhaar numbers, and
API keys or tokens become `[EMAIL]`, `[SECRET]` and so on. Long text is cut at `tracing.max_field_chars`.

## Example (a real stub run, records shortened)
```json
{
  "trace_version": "0.1", "run_id": "ee9aae9c8374494d", "case_id": "smoke-1", "user_id": "demo",
  "mode": "ask", "runner": "stub",
  "config": {"name": "base", "version": "0.2.0", "hash": "803a672dd277",
             "experiment": {"agent_mode": "team", "defences": true, "memory": true, "lessons": false,
                            "playbook_path": "config/playbook.json", "extraction": "schema", "retrieval_index": "both"},
             "models": {"supervisor": "openai/gpt-4.1", "specialist": "openai/gpt-4.1-mini", "...": "..."}},
  "started_at": "2026-11-22T10:40:09.626+00:00", "latency_ms": 1.1, "status": "ok", "error": null,
  "totals": {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "cost_complete": true},
  "input": {"question": "which recipes need no oven?"},
  "output": {"answer": "Found 3 match(es) in your saves.", "citations": ["rec1", "rec2", "rec3"],
             "records": [{"id": "rec1", "title": "No-oven paneer wrap", "...": "..."}], "blocked": null},
  "events": [
    {"t_ms": 0.5, "type": "retrieval", "name": "store.search", "hits": ["rec1", "rec2", "rec3"]},
    {"t_ms": 1.1, "type": "guardrail", "name": "output_citations", "blocked": false, "violations": []}
  ]
}
```
An LLM event from a real `ChatOpenAI` call looks like:
`{"t_ms": 16.0, "type": "llm", "name": "openai/gpt-4.1-mini", "agent": "answerer", "tokens_in": 57, "tokens_out": 9, "cost_usd": 3.72e-05, "latency_ms": 15.6, "error": null}`

## Report numbers this supports
Per configuration: task success (from `output` vs gold), blocked runs, `budget_exceeded`, `timeout` and `error`
counts, cost per case (`totals.cost_usd`), median and 95th-percentile `latency_ms`. Failed and timed-out runs
are traces too, so they are never silently dropped.
