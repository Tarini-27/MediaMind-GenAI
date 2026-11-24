"""All Prometheus metrics in one place (registered once). Grafana panels and the alert read these."""
from prometheus_client import Counter, Histogram

REQS = Counter("mediamind_requests_total", "Requests", ["endpoint", "outcome"])
LAT = Histogram("mediamind_request_seconds", "Latency", ["endpoint"])
BLOCKS = Counter("mediamind_guardrail_blocks_total", "Guardrail blocks", ["layer"])

RUNS = Counter("mediamind_runs_total", "Runs by mode and final status", ["mode", "status"])
RUN_SECONDS = Histogram("mediamind_run_seconds", "Run latency", ["mode"],
                        buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120))
RUN_COST = Counter("mediamind_cost_usd_total", "Model cost in USD (as reported by the provider)", ["model"])
TOKENS = Counter("mediamind_llm_tokens_total", "LLM tokens", ["model", "direction"])
LLM_CALLS = Counter("mediamind_llm_calls_total", "LLM calls", ["model", "outcome"])
TOOL_CALLS = Counter("mediamind_tool_calls_total", "Tool calls through the hooks", ["tool", "outcome"])
