"""Single config loader. Import `get_config()` everywhere; never hardcode models, prompts or flags.

Experiments are config files, not code changes. An experiment file names a parent and overrides only
what differs:

    # config/experiments/e2_defences_off.yaml
    extends: ../mediamind.yaml
    experiment:
      defences: false

Run with it:  MEDIAMIND_CONFIG=config/experiments/e2_defences_off.yaml  (one config per process).
Every trace records the config's name, version and hash, so each result is tied to the exact settings.
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "mediamind.yaml"

try:  # local runs read keys from .env; real environment variables (e.g. from Compose) win
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass


class Models(BaseModel):
    supervisor: str
    specialist: str
    judge: str
    embeddings: str
    guard: str


class LLM(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"    # the key itself lives only in .env
    timeout_s: float = 60
    max_retries: int = 2
    temperature: float = 0.0
    # Fallback USD per 1M tokens, used only when the provider does not report cost.
    # Fill from https://openrouter.ai/models if needed; empty means "cost unknown", never a guess.
    pricing: dict[str, dict[str, float]] = {}


class Experiment(BaseModel):
    agent_mode: str = "team"          # c0_workflow | c1_single_agent | team        (E1)
    defences: bool = True             # guardrails and permission/approval checks    (E2)
    memory: bool = True
    lessons: bool = False             # Reflexion playbook                           (E3)
    playbook_path: str = "config/playbook.json"
    extraction: str = "schema"        # schema | free_form
    retrieval_index: str = "both"     # both | records | chunks


class Budgets(BaseModel):
    """Equal resources for every configuration (E1 needs the same budget). Enforced even with defences off."""
    max_tool_calls_per_run: int = 25
    max_tokens_per_run: int = 60000
    max_cost_usd_per_run: float = 0.05
    max_seconds_per_run: float = 120


class Guardrails(BaseModel):
    max_upload_mb: int = 25
    max_video_mb: int = 100
    max_video_seconds: int = 180
    allowed_types: list[str]
    classify_confidence_threshold: float = 0.70


class Tracing(BaseModel):
    dir: str = "data/traces"          # one JSON file per run; the evaluation harness reads these
    max_field_chars: int = 2000       # long text in traces is truncated
    capture_content: bool = True      # record prompts and replies of model calls (scrubbed, truncated)
    langfuse: bool = False            # optional export to Langfuse (keys in .env)


class Auth(BaseModel):
    required: bool = False            # false = no login screen; everyone is default_user (team development)
    default_user: str = "demo"
    session_hours: int = 168          # a login lasts a week
    cookie_secure: bool = False       # true behind HTTPS
    max_failed_logins: int = 5        # then the account is locked for lockout_minutes
    lockout_minutes: int = 5
    history_size: int = 50            # recent searches kept per user


class Config(BaseModel):
    name: str = "base"
    version: str
    models: Models
    llm: LLM = LLM()
    experiment: Experiment
    budgets: Budgets
    guardrails: Guardrails
    tracing: Tracing = Tracing()
    auth: Auth = Auth()
    permissions: dict[str, list[str]]
    write_tools: list[str]
    prompts: dict[str, str] = {}
    # set by the loader, not by the file
    source: str = ""
    hash: str = ""


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"config 'extends' loop at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    parent = data.pop("extends", None)
    if parent:
        data = _deep_merge(_read((path.parent / parent), seen + (path,)), data)
    return data


def load_config(path: str | os.PathLike | None = None, **experiment_overrides) -> Config:
    """Load config (following `extends`). Overrides are for tests; experiments use config files."""
    path = Path(path or os.environ.get("MEDIAMIND_CONFIG", DEFAULT_PATH))
    if not path.is_absolute() and not path.exists():
        path = ROOT / path
    data = _read(path)
    data["experiment"] = {**data.get("experiment", {}), **experiment_overrides}
    cfg = Config(**data)
    canonical = json.dumps(cfg.model_dump(exclude={"source", "hash"}), sort_keys=True, default=str)
    cfg.hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    cfg.source = str(path)
    return cfg


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()
