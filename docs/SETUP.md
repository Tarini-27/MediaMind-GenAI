# MediaMind

Your media, made searchable. GenAI capstone: upload photos/screenshots, classify + extract into
structured records, approve every save, then ask questions and get cited answers.

## Run it (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_media.py          # synthetic gallery tiles
export PYTHONPATH=src
uvicorn mediamind.api.main:app --port 8000   # terminal 1
streamlit run ui/app.py                      # terminal 2 -> http://localhost:8501
pytest -q                                    # 25 tests
```

With Docker: `cp .env.example .env && docker compose up --build` (UI :8501, API :8000, Prometheus :9090, Grafana :3000).

## What exists today vs what each role plugs in

| Piece | State | Owner |
|---|---|---|
| Versioned config + experiment flags (`config/mediamind.yaml`) | done | R4 (everyone imports `mediamind.config`) |
| Approval gate (payload hash, edit voids approval, single use) | done + tested | R4 |
| Guardrails (PII mask, injection scan, upload checks, citation ownership) | rule layer done + tested | R4 |
| Hooks (permissions, budget, user_id injection) | done + tested | R4 |
| FastAPI + Prometheus metrics | stub endpoints | R4 |
| Instagram-style gallery UI, search bar, approvals queue | working on stub data | R4 / any |
| `api/store.py` (library, search) | **in-memory stub** | R2 replaces with SQLite + hybrid retrieval |
| `/ask` answer logic | **keyword stub** | R3 replaces with the LangGraph team |
| Gold data, eval runner, red-team suite | not started | R1 |

## Contracts to agree before replacing stubs
- Record schema (title, category, fields, source spans) -> R1 + R2 + R3
- MCP tool names and signatures: see `permissions` in the config
- `store.py` function names stay stable: `get_item`, `list_items`, `search`, `save_item`

See `docs/permission_matrix.md`. Never commit `.env` or real user data (synthetic/consented only).
