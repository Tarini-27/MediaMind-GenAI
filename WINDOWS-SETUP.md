# MediaMind on Windows / Cursor

Open this **mediamind** folder in Cursor, rather than its parent planning folder.
The local environment is `.venv`, created with Python 3.12. No activation or
PowerShell execution-policy change is necessary for the commands below.

## Run

Double-click `Start-MediaMind.cmd`, or run in Cursor's PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe start.py
```

Open http://127.0.0.1:8765. Stop with Ctrl+C. If the port is occupied, use
`start.py --port 8768`. Cursor also has a **MediaMind: start** task and an F5
debug configuration named **MediaMind: run and debug**. If prompted for an
interpreter, select `.venv\Scripts\python.exe`.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pip check
```

The supplied tests mock model providers. Passing them does not establish live
model accuracy or course-provider access.

The Windows test command disables pytest's optional result cache to avoid local
cache-write issues observed in this OneDrive workspace.

## Credentials and media

Start without credentials to explore the interface and synthetic demo notes.
Use **Model connection** to supply your own provider credentials, or copy
`.env.example` to `.env` and fill it locally. An OpenRouter key and an accessible
model ID are needed for generated text-agent answers. Media extraction and
embeddings currently require Gemini access separately. No live paid model calls
are part of environment installation.

The GitHub upload excludes the 50-video bundle. Copy the separately shared
`imports/reels-50` folder, including its manifest and posters, into this project,
or upload your own videos through the app. Do not interpret an empty feed as
a failed dependency installation. The reranker model downloads on first use.

## Dependencies

Use the project's `requirements-semantic.txt` for the full local Python setup.
CPU-only PyTorch is sufficient. Dependency versions actually installed locally
are captured in the ignored `requirements-windows.local.txt` file when setup
finishes. The supplied lock files describe another machine's tested environment.

There is no npm build step: the UI is plain HTML/CSS/JavaScript. The local Python
app supports in-process MCP and a local Qdrant store. Docker Desktop is optional
for local development; it is needed to run the separate Compose deployment with
Prometheus/Grafana. No local-runtime FFmpeg invocation was found in the source.

The new `.gitignore` excludes `.venv`, credentials, imported media and runtime data.
Editor configuration, launchers and this guide are reviewable uncommitted files.

The first Windows test run exposed open SQLite handles during temporary database
cleanup. Local compatibility changes now close the application connection after
each transaction and release the graph checkpointer on shutdown or replacement.
Agent tests explicitly release the checkpointer before removing their fixtures.
These source/test changes are also uncommitted for team review.

## Verified on 22 November 2026

- Source checkout: `bf80098` (`initial commit`) plus the local setup/cleanup changes.
- Python 3.12.10; CPU-only PyTorch 2.15.0+cpu.
- `pip check`: no broken requirements.
- Core and semantic-search package imports: passed.
- Existing suite: **62 passed in 55.92 seconds**, with optional pytest caching disabled.
- Real subprocess startup: `/health`, `/`, `/assistant.js` and `/metrics` passed.
- Cursor's Python and debugger extensions were already installed; project opened.
- No live model API requests, credentials or demo video bundle were needed for these checks.
- The smoke-test server was stopped after verification; use the launcher to start your session.

## Role 3 starting points

Read `capstone/graph.py`, `capstone/models.py`, `capstone/reflexion.py`,
`capstone/grants.py`, `tests/test_capstone.py`, and `evaluation/README.md`.
Reproduce the baseline before changing behaviour. Keep held-out evaluation
cases with Role 1.
