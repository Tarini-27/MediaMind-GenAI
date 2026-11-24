# MediaMind

**Your saved photos, screenshots and short videos, made searchable.** Upload an image or a video (up to 3 minutes),
have it classified and extracted into structured records, approve every save, then ask questions in plain language and
get cited answers. For videos, the answer will point to the moment that matters (a timestamp in the transcript).

GenAI capstone project (team of 4). This repo is the **foundation scaffold**: the control layer, API and
frontend are real and tested; the retrieval and agent layers are **stubs** that Roles 2 and 3 replace.

---

## 1. What is built today

| Area | Status | What it does |
|---|---|---|
| Versioned config + experiment files | Done, tested | One YAML file for models, prompts, budgets, permissions; each experiment is a small file in `config/experiments/` that overrides only its switches; every trace records the config's name, version and hash |
| Run tracing | Done, tested | Every run writes `data/traces/<run_id>.json`: every LLM call (model, prompt, reply, tokens, cost, latency, error), every tool call, guardrail and approval events, totals and status. PII and secrets scrubbed |
| Run endpoint | Done, tested | `POST /runs` wraps one run with a time limit, for the evaluation harness; Role 3's graph plugs in through a runner registry |
| Traced model access | Done, tested | `chat()` (plain HTTPS, no LangChain) and `get_chat_model("specialist")` (LangChain) read the model ID from the config, calls OpenRouter, asks for the real cost, records it, and enforces the token and cost budget |
| CI | Done | GitHub Actions runs the tests and the Angular build on every push (evaluation gate added Day 9) |
| Login and sessions | Built and tested, **switched off** (`auth.required: false`) while the team builds; everyone is `demo`. Turn on for the final demo | Sign-up and log-in, scrypt password hashes, HttpOnly session cookie (only its SHA-256 stored), lockout after 5 failed logins. **The user comes from the session, never from a `user_id` the browser sends.** Media files served to their owner only |
| Search history | Done, tested | Each user's recent searches (PII masked, blocked questions never kept) shown as suggestions under the search box; can be cleared |
| Approval gate | Done, tested | A human approves the *exact* payload. Editing it voids the approval. One use only |
| Guardrails | Rule layer done, tested | PII masking, prompt-injection scan, upload checks, citation ownership check |
| Tool hooks | Done, tested | Permission matrix, budget (always on), `user_id` injected by code, write tools need an approval, crashing tools become structured errors, every call traced |
| FastAPI backend | Real endpoints, stub intelligence | Items, ask, upload proposals, approvals, health, Prometheus metrics |
| Angular frontend | Working | Three panes after the proposal's sample screen: collections with counts and an approvals box, chat search with cited results, **save search results as a named collection** and **delete items** (both approved first), a detail pane with media and Summary / Fields / Text tabs; approvals drawer, upload dialog |
| Video upload and playback | Done, tested | mp4/webm up to 100 MB and 3 min, checked with ffprobe, thumbnail with ffmpeg, plays and seeks in the lightbox |
| Library database (SQLite) | Done, tested | Schema for users, items, collections and the approval queue; records and pending approvals survive restarts |
| Docker Compose | Wired, first full run pending | `docker compose up --build` starts the API and Angular (nginx); `--profile monitoring` adds Prometheus and Grafana |
| Tests | 118 passing | Approval gate, guardrails, hooks, API flows, uploads and video, database, run tracing and config |
| Retrieval (RAG), OCR, MCP tools | **Not built** | `search()` in `api/store.py` is a keyword stub (Role 2) |
| Agent team (LangGraph) | **Not built** | the `stub` runner answers by keyword search until Role 3 registers the graph (Role 3) |
| Evaluation (gold set, runner, red team) | **Not built** | Role 1 |

---

## 2. Architecture

```
  Browser ── Angular (4200) ──/api/*──▶ FastAPI (8000) ──▶ control layer ──▶ store ──▶ SQLite
                                            │                 │
                                            │                 ├─ guardrails: PII mask, injection scan, upload checks
                                            │                 ├─ hooks: permissions, budget, user_id injection
                                            │                 └─ approval gate: payload hash, edit voids approval
                                            └─▶ /metrics ─▶ Prometheus ─▶ Grafana
```

How a save works (nothing is written until a human approves):

1. `POST /uploads/propose`: type and size checks, injection scan of any extracted text, then a **pending proposal**. The server assigns the stored file name, so uploads can't overwrite each other.
2. `POST /uploads/{id}/blob`: the bytes go to `data/uploads/pending/<id>/`, never to the public media folder. Images must really be images; videos must be readable by ffprobe and within the length limit, and get a thumbnail. The file's **sha256 is written into the payload**, so the approval covers the exact bytes. A refused file is deleted and its proposal rejected.
3. The proposal shows in the approvals drawer with an owner-only preview. The user can approve, edit or reject.
4. **Edit** may change only title, category and tags. The hash changes, so the earlier approval is void.
5. **Approve** binds the approval to the current hash. `execute()` recomputes the hash and re-checks the file's sha256 right before writing, so tampering with the record or swapping the file after approval is caught. Only then is the file moved into `data/media/` and the record saved. The approval is single use.
6. **Reject** deletes the pending file.

How a question works: `/ask` runs the injection scan on the question, masks PII, searches only the caller's records, then checks that every cited record ID exists and belongs to the caller. If nothing matches, it abstains instead of inventing an answer.

---

## 3. Tech stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI, Uvicorn, Pydantic v2 |
| Frontend | Angular 22 (standalone components, signals, new control flow), SCSS, TypeScript |
| Config | YAML + Pydantic loader |
| Observability | `prometheus_client`, Prometheus, Grafana |
| Tests | pytest, FastAPI TestClient |
| Packaging | Docker, Docker Compose, nginx (serves Angular, proxies `/api`) |
| Media processing | Pillow (image checks), ffprobe (video checks), ffmpeg (video thumbnails) |
| Planned (other roles) | LangGraph, FastMCP, Chroma or Qdrant, BM25 + bge-m3 + reranker, Tesseract/vision OCR for images, faster-whisper (speech to text) and PySceneDetect (key frames) for videos, Langfuse |

The frontend only talks to the API through `/api/*`, so either side can change without touching the other.

---

## 4. Repo layout

```
config/
  mediamind.yaml        models, LLM settings, experiment flags, budgets, tracing, permission matrix, write tools, prompts
  experiments/          one small file per experiment (extends mediamind.yaml)
  prometheus.yml
src/mediamind/
  config.py             load_config() / get_config(); follows `extends`, computes the config hash, loads .env
  runs.py               run_scope(): run IDs, trace files, budget checks
  runners.py            execute_run() and the runner registry (stub today; Role 3 registers the graph)
  llm.py                chat() (plain HTTPS) and get_chat_model() (LangChain): traced, budgeted models from the config
  metrics.py            all Prometheus metrics
  control/
    approval.py         ApprovalGate: propose / approve / edit / reject / execute
    guardrails.py       mask_pii, scrub (PII + secrets), detect_injection, upload/image/video checks, check_citations
    hooks.py            call_tool(): the only way agents reach tools
    repos.py            SQLite storage for approval proposals
  db.py                 schema, connection helper, seed data
  api/
    main.py             FastAPI app and endpoints
    store.py            library on SQLite: get_item, list_items, search (keyword STUB), save_item, soft_delete
frontend/
  src/app/core/         models.ts, api.service.ts (HTTP), store.service.ts (signal state)
  src/app/components/   header, sidebar, results, detail, approvals, upload
  proxy.conf.json       dev: /api -> localhost:8000
  Dockerfile, nginx.conf
tests/                  test_approval, test_guardrails, test_api, test_store, test_uploads, test_runs,
                        test_llm_chat, test_llm_langchain (skipped where LangChain is blocked)
.github/workflows/ci.yml       tests + Angular build on every push
scripts/make_sample_media.py   synthetic gallery tiles and a sample video (video step needs ffmpeg)
scripts/init_db.py             create / reset / seed the database
scripts/smoke_run.py           checks the run endpoint and traces; --live makes one real OpenRouter call
scripts/try_vision.py          experiment: send real images to the vision model, see what it reads (traced)
data/traces/                   one JSON trace per run (git-ignored)
data/mediamind.sqlite          the database (created on first start, git-ignored)
data/media/             9 sample image tiles and a 9-second sample workout video (synthetic only)
docs/permission_matrix.md      which agent may call which tool
docs/database.md               schema, rules and contract for the database
docs/trace_format.md           what a trace contains (proposed for Role 1)
```

---

## 5. Run it

### Prerequisites
- Python 3.11+
- **ffmpeg** (for video): `winget install Gyan.FFmpeg` on Windows, then open a new terminal. Without it, images still work and video uploads are refused with a clear message. Some Windows machines let ffmpeg install but block it from running (Application Control). The API detects this and refuses video with that reason, and the video tests are skipped; run the backend in Docker or WSL to use video.
- **Node 22.22.3+ or 24.15+** (Angular 22 requirement)

### Backend (terminal 1)

PowerShell:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/make_sample_media.py
python scripts/init_db.py                    # optional: the DB is also created on first start
python -m uvicorn mediamind.api.main:app --app-dir src --port 8000
```

macOS / Linux:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_media.py
python -m uvicorn mediamind.api.main:app --app-dir src --port 8000
```

### Frontend (terminal 2)
```bash
cd frontend
npm install
npm start          # http://localhost:4200  (proxies /api to :8000)
```

Open http://localhost:4200. Login is **off** by default (`auth.required: false` in `config/mediamind.yaml`), so you go straight to the demo library.

**Turning login on** (for the final demo): set `auth.required: true` and restart the API. You then get a login screen: **`demo` / `mediamind-demo`** opens the sample library, or sign up for an empty one.
The demo password is for local use only: set `MEDIAMIND_DEMO_PASSWORD=...` in `.env` to change it (it applies when the demo user is first created, so on an existing database run `python scripts/init_db.py --reset` or sign up a new user).

Put your OpenRouter key in `.env` (`OPENROUTER_API_KEY=...`). It is loaded automatically and never committed.

### Tests and smoke checks
```bash
PYTHONPATH=src pytest -q       # PowerShell: $env:PYTHONPATH="src"; pytest -q
python scripts/smoke_run.py          # with the API running: logs in as demo, 3 runs through POST /runs, traces checked
python scripts/smoke_run.py --live   # plus one real OpenRouter call (a fraction of a cent) to check cost tracking
python scripts/try_vision.py my_screenshot.png   # what the vision model reads from a real image
```

### Running an experiment
```bash
MEDIAMIND_CONFIG=config/experiments/e2_defences_off.yaml python -m uvicorn mediamind.api.main:app --app-dir src --port 8000
```
Each trace then carries `config.name = "e2_defences_off"` and that config's hash.

### Docker
```bash
cp .env.example .env      # optional; Compose starts without it
docker compose up --build
```
In Docker the database lives in a Docker volume (`mediamind-state`), because SQLite is slow or hangs on a folder shared from Windows. Media, uploads and traces stay in `./data`. `docker compose down -v` deletes the volume and so the database; the app reseeds the demo data on the next start.
App on `:4200`, API on `:8000`. Monitoring is opt-in, because its images are large downloads:
`docker compose --profile monitoring up --build` adds Prometheus on `:9090` and Grafana on `:3000`.

---

## 6. API

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness (no login) |
| `POST /auth/signup` | `{username, password}`: creates the account and logs in (sets the `mm_session` cookie) |
| `POST /auth/login` | `{username, password}`: sets the cookie. Wrong password and unknown user give the same 401; 5 failures lock the name for 5 minutes (429) |
| `POST /auth/logout` | Deletes the session on the server and the cookie |
| `GET /auth/me` | `{user_id}` of the session, or 401 |
| `GET /history?q=` | The caller's recent searches, newest first, containing `q` |
| `DELETE /history` | Clears the caller's search history |
| `GET /metrics` | Prometheus metrics: requests, runs by status, run latency, LLM tokens and cost, tool calls, guardrail blocks |
| `POST /runs` | Run one request end to end (time-limited) and write its trace; body `{user_id, mode, question, case_id, input}` |
| `GET /runs/{run_id}?user_id=` | A run's trace, owner-only |
| `GET /items?user_id=&category=&collection=` | List a user's records, by category or by one of their collections |
| `POST /items/{id}/delete` | Body `{user_id}`: a pending `library.soft_delete` proposal; the item stays until approved. Someone else's item answers 404, like a missing one |
| `GET /collections?user_id=` | The user's own collections with live item counts |
| `POST /collections/propose` | Body `{user_id, name, item_ids}`: a pending `library.collect` proposal (nothing created yet). Items must exist and be the caller's; the name is scanned for injection |
| `POST /ask` | The UI's search: a traced run returned as `{answer, citations, records, blocked, run_id}` |
| `POST /uploads/propose` | Checks then a pending save proposal (nothing saved yet) |
| `POST /uploads/{id}/blob?user_id=` | Attach the file bytes once; checked, hashed, held in the pending folder |
| `GET /uploads/{id}/preview?user_id=` | Owner-only preview of a pending file (thumbnail for videos) |
| `GET /media/{file}` | Approved images, videos and video thumbnails; supports range requests, so videos can seek |
| `GET /approvals?user_id=` | Pending proposals for a user |
| `POST /approvals/{id}/approve` | Approve and write (single use): saves the upload, creates or extends the collection, or soft-deletes the item |
| `POST /approvals/{id}/edit` | Change payload; voids any earlier approval. Only the title, category and tags of a save, or the name of a collection, can change. A delete cannot be edited (so it cannot be pointed at another item) |
| `POST /approvals/{id}/reject` | Reject; nothing written |

**With login off (the default now)**, nothing needs a login: the API uses `user_id` from the request, or `demo` if none is sent, and `GET /auth/me` answers `{user_id: "demo", login: false}`. Everything below applies once `auth.required: true`.

With login on, every endpoint except `/health`, `/metrics` and `/auth/*` needs a login (401 otherwise). The user is taken from the session cookie; a `user_id` in the body or URL is **ignored** while logged in. Other users' items, proposals and files look absent (404), never forbidden.

For the evaluation harness (Role 1): log in once with a `requests.Session()` as `scripts/smoke_run.py` does. `MEDIAMIND_AUTH=on` or `off` overrides the config setting; the unit tests use it to test both modes.

---

## 7. Config and experiment flags

`config/mediamind.yaml` is the only place for model IDs, prompts and flags. Nobody hardcodes them.
Each experiment is a small file in `config/experiments/` that `extends` the base and overrides only its
switches, so running an experiment never needs a code change:

| Flag | Values | Used for |
|---|---|---|
| `experiment.agent_mode` | `c0_workflow`, `c1_single_agent`, `team` | E1 (workflow vs single agent vs team) |
| `experiment.defences` | `true` / `false` | E2 (guardrails off vs on; attack success and false blocks) |
| `experiment.memory` | `true` / `false` | Memory on vs off |
| `experiment.lessons` | `true` / `false` | E3 (Reflexion playbook) |
| `experiment.extraction` | `schema` / `free_form` | E4 candidate (Role 1's plan) |
| `experiment.retrieval_index` | `both` / `records` / `chunks` | E4 candidate (the proposal's ablation) |

**E4 needs a team decision:** the proposal defines E4 as records vs chunks vs both; the Day 5/9 plan says free-form vs
schema-validated extraction. Both switches exist; pick one and delete the other's files.

Budgets (`max_tool_calls_per_run`, `max_tokens_per_run`, `max_cost_usd_per_run`, `max_seconds_per_run`) apply to
every configuration, including defences off, so experiments compare systems with the same resources. The values are
placeholders until measured from real traces.

### Permission matrix
Defined in the config, documented in `docs/permission_matrix.md`. Only the **organizer** agent may call
write tools (`library.save`, `library.update`, `library.move`, `library.collect`, `library.soft_delete`), and only behind the
approval gate. A test fails if any other agent is granted a write tool.

---

## 8. Frontend

Laid out like the sample screen in the proposal (section 11): three panes, purple accent, warm red for approvals.

- **Login screen:** Log in / Sign up tabs; shown whenever there is no valid session (including when one expires mid-use: any 401 returns you here). The page never sees the session token.
- **Top bar:** the name, the question box ("Ask about your saved media") where the agent answers, **+ Upload media**, and your initial, name and **Log out**.
- **Search suggestions:** clicking the search box shows your **recent searches**; typing filters them. Arrow keys and Enter pick one, **Clear** wipes the history. They are yours only and kept on the server, so they follow you to another browser.
- **Left, collections:** All items, Recipes, Workouts, Places, Learning, Other, each with its count. Under them, **My collections**: the ones you saved from searches, with counts. At the bottom, the **Approvals** box shows how many changes are waiting (red when any are) and opens the approvals drawer.
- **Middle, browsing:** the chosen collection as cards (image or video thumbnail with a ▶ badge, title, category and type).
- **Middle, asking:** your question as a chat bubble, the answer, the cited results as cards ("cited as rec4"), a citations line, a **Save N results as collection “your question”** button, and a **follow-up** box at the bottom. The best match opens in the detail pane automatically. A blocked question shows the guardrail's reason in red.
- **Right, detail:** the image, or the video in a player with seeking; title, category, type, saved date and record ID; tabs **Summary**, **Fields** (filled by the extraction agent later) and **Text** or **Transcript** (filled by the reader later); **Delete** proposes a delete (the button then shows "delete waiting in Approvals" so it isn't proposed twice); Edit and Move are still disabled until the Organizer agent exists. On narrow screens it slides over the page.
- **Approval popup:** whatever you just asked for (an upload, a collection, a delete) opens at once as a popup in the middle of the screen: "Save this to your library?", "Save this collection?" or "Delete this item?", with the same card, hash, editable title or name, and Approve / Reject. Editing keeps the popup open with the new hash. **Decide later** closes it and leaves the proposal in the Approvals queue. Proposals made by the agents later will wait in the queue rather than pop up.
- **Approvals drawer:** opens from the Approvals box; the full queue, including anything put off with Decide later. Each card shows a preview of the pending file (a video's thumbnail and its length). Editing a title turns the button into **Save edit**, and Approve is only available after the new hash exists, which makes the "edit voids approval" rule visible.
- **Collections from search:** the save button only *proposes*. The drawer shows a folder card ("new collection" or "add to collection", the item count, the item titles) with the name editable; changing the name voids the approval as with uploads. On approval the collection appears under My collections. Items stay in their own category; a collection is a label over them, not a move. Saving again under the same name (any case) adds to the existing collection instead of making a second one. Deleted items drop out of the counts.
- **Deletes:** the drawer shows a red-edged card with the item's picture, title and category, **Approve delete** and **Keep it**. Approving hides the item from the library, search and collections; the row stays in the database with `deleted_at` set, so it can be restored by hand.
- **Upload dialog:** pick a photo, screenshot or short video (PNG, JPEG, WebP, MP4, WebM), then a title and category. Videos preview in the dialog. It creates a proposal and waits for approval.
- **State:** one `Store` service built on signals. Components read signals; only the store calls HTTP.
- Light and dark theme follow the system. Under 1100 px the detail pane slides over; at phone width the collections become a row of chips.

---

## 9. Tests (118)

| File | Covers |
|---|---|
| `test_approval.py` | Approve then write; write without approval fails; **edit voids approval**; tampering after approval is caught; reject writes nothing; approval is single use; other users cannot see or approve; hash ignores key order but not values |
| `test_guardrails.py` | PII masking; injection in OCR text flagged and clean recipe text not flagged; upload checks; citations must exist and belong to the caller; only organizer has write tools; permission denied; write needs approval; budget enforced; `user_id` injected by the hook; defences-off skips checks (E2) |
| `test_store.py` | Saved item survives reconnect; list and search scoped to user; soft delete hides a record and only the owner can delete; seed runs once and can be disabled; **pending proposal and approval survive a restart**; executed approval cannot be replayed; edit voids approval in the database; **tampering with the stored payload is caught**; concurrent execute writes exactly once; a failed write gives the approval back; other users cannot touch a proposal |
| `test_uploads.py` | Server-assigned file names; unapproved files stay out of `/media`; approve moves the file; approve without a file refused; file uploaded only once; fake image refused and cleaned up; **swapping the file after approval is caught**; edit cannot change file fields; reject deletes the pending file; preview is owner-only; video gets a thumbnail, plays and supports range requests; fake and over-long videos refused; video size limit |
| `test_runs.py` | `/runs` writes a trace with every agreed field; `/ask` and approvals are traced; blocked, error and **timeout** runs are recorded (a late worker can't overwrite a timeout); a registered runner replaces the stub; tool calls, blocks and crashes traced; LLM tokens, cost and latency recorded; unknown cost stays null; token budget stops the next call; budget applies with defences off; **API keys and PII never reach a trace**; models come from the config; experiment files override only their switches |
| `test_collections.py` | Nothing created before approval; collection lists only its items and another user sees none; other users' or unknown items, empty names and empty lists refused; **editing the name voids the approval** and only the name can change; the same name in any case merges; an injected name is blocked; approval single use and reject creates nothing; deleted items drop out of counts; collections are per user |
| `test_delete.py` | Nothing deleted until approved; the delete is soft (row kept); reject keeps the item; another user's item can't be proposed or approved; **a delete can't be edited to point at another item**; approval single use, and a second delete of the same item fails cleanly; a deleted item leaves search and collection counts |
| `test_auth.py` | Nothing works without login; **the session decides the user, a claimed `user_id` is ignored**; demo login sees the seeded library; passwords stored as scrypt, session tokens only as hashes; cookie is HttpOnly and SameSite; sign-up rules and taken names; wrong password and unknown user look the same; seed users without a password can't log in; lockout after 5 failures; logout makes an old cookie useless; expired sessions refused; media only for its owner; history newest first, no duplicates, `%` not a wildcard; history private, PII masked, blocked questions not kept, clearable |
| `test_auth_off.py` | With login off: `/auth/me` says demo and no login, the demo library loads without a user_id, scripts can still choose a user, and an old login cookie is ignored |
| `test_api.py` | Per-user isolation; ask cites only own records and abstains on no match; injection blocked on `/ask`; bad upload type and embedded injection rejected; nothing saved until approved, edit changes the hash, approval single use; metrics exposed |

The frontend was also driven end to end in a real browser (gallery, category switch, search, injection block, lightbox, image and video upload, approval preview, edit, approve, video playback, a fake video refused; wrong password, log in, owner-only thumbnails load, recent-search suggestions with filter and keyboard, log out, sign up a fresh user with an empty library and no suggestions, still logged in after reload; search, save results as a collection, approve it from the popup after renaming it, open it from the sidebar; put a delete off with Decide later and find it in the queue; upload and approve from the popup; delete an item, approve it, see it gone and the counts drop) with no console errors.

---

## 10. Known limits (be honest in the viva)

- The database is a single SQLite file with no migrations: a schema change means `python scripts/init_db.py --reset`. Records and approvals persist, but the LangGraph checkpointer (Role 3) is a separate file still to come.
- The only runner is the **stub** (keyword match, no LLM). Traces say `runner: "stub"` so stub results can't be mistaken for agent results.
- Real OpenRouter calls were tested against a local stand-in server with OpenRouter's response format, not OpenRouter itself. Run `python scripts/smoke_run.py --live` once to confirm with your key.
- **LangChain can be blocked on Windows** by Application Control (Smart App Control or a company policy), because its dependencies include compiled files (`xxhash`, `orjson`, `zstandard`, `tiktoken`). The API and `mediamind.llm.chat()` don't need LangChain. LangGraph agents do, so where that happens, run the backend in Docker or WSL, where the policy doesn't apply.
- `docker compose up --build` has not been run end to end yet (the compose file validates). Do it once on a clean machine; that is also the guide's install evidence.
- Langfuse export is not wired; the JSON traces are the source of truth for the harness.
- No streaming responses yet (the guide asks for FastAPI streaming).
- The injection scan is **regex rules** only. Prompt Guard 2 and Llama Guard 4 plug in through `detect_injection(classifier=...)` and are not wired yet. Rules alone are bypassable by paraphrase, which is why E2 and the red-team suite matter.
- `ApprovalGate` is framework-agnostic and **not yet inside LangGraph `interrupt()`**.
- Hooks (`call_tool`) and `get_chat_model` are tested but **not yet used by any agent**, since the agents do not exist yet.
- Login is username and password only: no e-mail verification, password reset or second factor. The failed-login lockout is kept in memory, so it resets on restart and isn't shared between several API processes. There is no CSRF token; the cookie is `SameSite=Lax` and every write is a JSON POST, which blocks the usual cross-site form attack. Set `auth.cookie_secure: true` once the app is served over HTTPS.
- The demo account has a known default password for local demos. Change it with `MEDIAMIND_DEMO_PASSWORD` before anyone else can reach the app.
- Video is uploaded, validated, stored and played, but not **processed** yet: no transcript, frame extraction or timestamped citations (Role 2: faster-whisper, PySceneDetect). Its `text` is empty until then, so `/ask` only finds videos by title.
- No duplicate detection (imagehash) yet. Sample media is synthetic.

---

## 11. Who plugs in where

| Piece | Owner | Keep stable |
|---|---|---|
| Hybrid retrieval inside `search()`, MCP tools, OCR, vector index (library DB already exists) | Role 2 | function names `get_item`, `list_items`, `search`, `save_item`, `soft_delete`; always filter by `user_id` |
| Graph registered as a runner (`@register("team")` etc. in `runners.py`), specialists using `get_chat_model` and `call_tool`, planner, Reflexion; `ApprovalGate` inside `interrupt()` | Role 3 | the `ask` output shape `{answer, citations, records, blocked}` |
| Gold set, eval runner, judge calibration, red-team suite, report | Role 1 | record schema agreed on day 1 |
| Control layer, config, Compose, tracing, CI gate, threat model, E2 | Role 4 | permission matrix, config keys |

### Role 4 to-do
Day 5 (Wed 25 Nov)
- [x] FastAPI endpoint wraps a run (`POST /runs`)
- [x] Every run writes a trace with run ID, LLM and tool calls, cost, latency and errors (`docs/trace_format.md`)
- [x] One versioned config holds model IDs and prompts (prompts are Role 3's to fill)
- [ ] `docker compose up --build` checked on a real machine
- [ ] Trace format confirmed by Role 1

Day 7 (Fri 27 Nov)
- [ ] Review the held-out cases against the written policy

Day 9 (Sun 29 Nov)
- [ ] Threat model one-pager (`docs/threat_model.md`)
- [ ] FastAPI streaming (guide's minimum bar)
- [ ] Wire `ApprovalGate` into LangGraph `interrupt()` (pair with Role 3, about one hour)
- [ ] Prompt Guard 2 and Llama Guard 4 as extra layers
- [ ] Langfuse tracing in the post-tool hook
- [ ] Grafana dashboard and one alert
- [ ] CI eval gate and one explained failed run
- [ ] Clean-machine install check
- [ ] Real auth to replace the `demo` user
- [x] Uploads held in a pending folder and moved on approval; bytes bound into the approval
- [ ] Per-user check on `/media` (see threat model)

## 12. Conventions
- Never commit `.env`, real keys or real personal media. Use synthetic or consented data only.
- Held-out evaluation cases live in `data/heldout/` (git-ignored) and the agent must not read them.
- Small PRs, merged daily. Add your tool or agent to `docs/permission_matrix.md` as you build it.
