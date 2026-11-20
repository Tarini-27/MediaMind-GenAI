# MediaMind — your saved world

An Instagram-inspired saved-content prototype for videos, photos and notes across food, travel, workouts, learning, lifestyle and other topics.

The prototype simulates the saved-post workflow using user-provided media files. It does not connect to Instagram or import a private account's Saved collections.

## Demo videos

This source-code upload excludes the large demo media and private local data.
To restore the 50-video feed, extract the separately shared `MediaMind-Latest-Project.zip` and copy its `MediaMind/imports/reels-50` directory into this project at `imports/reels-50`. That folder contains the videos, source manifest, metadata and posters.
Alternatively, start the app and add your own videos to the feed. Save selected videos to a collection to prepare them for search. Each teammate supplies their own API credentials.

## Start

The full app requires Python 3.12+ and a modern browser. For a new machine:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-semantic.txt
```

`requirements.lock` records the tested core environment; `requirements-semantic.lock` records the full tested local environment. GPU/CPU package wheels vary by platform. The small local reranker downloads on first search; later searches reuse the cache.

On this Mac, double-click **Start Gather.command** and keep the terminal open. Otherwise run this from the project folder:

```sh
.venv/bin/python start.py
```

Open http://127.0.0.1:8765. If that port is occupied, run `.venv/bin/python start.py --port 8768` and use that address. Stop the server with Ctrl+C.

## Ask your saves — new

Choose **Ask your saves** in the navigation.

- Ask a question, compare saved sources or continue with a follow-up.
- Choose topic, collection or saved-date filters. The saved date is the local import date.
- With a model connection, a LangGraph supervisor plans the request, a retriever finds evidence, a writer drafts claims and a verifier checks support. One repair attempt is allowed. Progress streams into the page.
- Without a key, the app returns labelled source excerpts with citations. It does not pretend to generate an answer or resolve conversational references with an LLM.
- Click a source chip to open the original. A valid video timestamp seeks the clip; model-reported timing remains approximate.
- Check **Review answer for notebook** before asking to request a notebook note. Approve, edit the title and review again, or reject. Factual edits require a new evidence-backed request. Approval is tied to the exact content and source versions.
- Open **Model connection** to use OpenRouter for text agents. Gemini remains the media-extraction/embedding provider. Keys entered here are current-page only.
- Optional preferences require explicit consent; they can be changed or deleted. **New chat** deletes the current chat checkpoints. A pending review can be restored after refreshing or restarting.

Old notes without retained evidence remain visible in Saved but cannot support passage-cited chat. Open them and choose **Reanalyse original**, then review and approve the new extraction. Reanalysis needs your model key.

## The feed-to-save workflow

1. Open the app on **Feed**, browse the local discovery videos and play any clip.
2. Tap its bookmark, choose one or more collections (or create one), then **Save & prepare for search**.
3. The same action authorizes sending that selected media to Gemini. Connect your key once when prompted; the pending save continues after the connection succeeds.
4. A background worker extracts evidence-linked notes, checks their structure/evidence references, creates a 768-dimensional embedding and then marks the save **Search ready**.
5. Keep browsing during **Preparing**. Search uses completed saves; unsaved feed videos never enter retrieval. Browsing makes no model calls.
6. Saving to another collection reuses the same saved source, note and embedding. Failed embedding preparation retains its extraction so retry does not reanalyse the video.
7. **Add a video** adds a local upload to the feed first. Use its bookmark to save and prepare it. Existing saved sources remain in Saved.

The curated feed prefers `imports/reels-50/sources.json` (50 mixed videos: 47 with English speech, 3 text-led), with `imports/reels-100/sources.json` as a fallback and local files, not Instagram account access. Sources/credits remain in the manifest. Original text demo reels are labelled. Add the media folder when sharing the app; otherwise the feed contains only local uploads.

Automatic private indexing is distinct from an agent action that publishes a notebook entry. Automatic notes are explicitly **AI generated**, not human reviewed. They retain evidence and unknowns; automated checks cannot establish that every model interpretation is correct. Internally the historical `approved` status means eligible for retrieval; `auto_index` and `note_review` distinguish machine-prepared notes from legacy human-approved ones. Only a completed note plus embedding receives the new UI's **Search ready** label.

**Ask your saves** retains the LangGraph supervisor, specialists, hybrid retrieval, query rewriting, verification, memory and exact-payload approval for notebook writes. Its advanced filters/preferences/notebook controls are collapsed by default. **Course tools** contains processing details and the capstone checklist. The deterministic/manual review API is retained as a baseline and for existing notes; it is not part of the everyday feed-save flow.

## Collections

- Switch between **All saves** and **Collections**.
- Choose **New collection** to create one.
- The bookmark icon on each card opens collection assignment. One post can belong to several collections.
- Open a collection to see only its saves. Searches made there are restricted to that collection.
- Deleting a collection keeps its original saved posts in All saves.
- **Remove save** deletes the original media, cached preview, note, vector, trace and collection memberships for that source. Exported copies and provider-side records are outside that deletion.

Initial collections: Food & recipes, Places to go, Move & feel good, and Learn something. Existing recipe notes from the earlier POC remain intact and are associated with Food & recipes on first migration when they contain ingredients.

## General media analysis

The extraction format now supports:

- A title, summary and category for any supported source.
- Evidence-linked key takeaways, mentioned entities and tags.
- Instructions only when the source actually demonstrates or states them.
- Optional recipe-specific ingredients and equipment evidence.
- Explicit unknowns instead of invented prices, quantities, opening hours, personal identities, nutrition or workout outcomes.
- Source quotations or visual observations, with approximate timestamps for video evidence.

The model is fallible. Source-text quotations are checked for exact presence in supplied text, but that alone does not establish support for a claim. Visual/audio evidence and timestamps are model-reported and require review. General-topic schemas and mocked-provider tests do not establish accuracy on every type of video.

## Model settings

Open **Model settings** in the sidebar. On narrow/mobile layouts, use the circular profile button at the top right.

- Enter a Gemini key for the current page session.
- The configurable default is `gemini-3.5-flash-lite`.
- **Check available models** lists generation models from Google. Listing alone does not establish generation access, video support or free-tier quota.
- **Test & use these settings** makes a small text request before accepting the key/model.
- Failed analyses use the currently selected model when retried; re-uploading is unnecessary.

A key can alternatively be configured using the `GEMINI_API_KEY` environment variable. API keys entered in the UI stay in browser/server memory for requests; they are not written to the app database or browser storage. Refreshing clears a UI-entered key.

Uploads added to the feed are local. Choosing Save & prepare for search explicitly starts AI analysis. Gemini analysis sends the selected file/text to Google. Semantic indexing sends note text, and semantic search sends a query. Quota and charges depend on your account. Do not include keys or private runtime data in a shared package.

## Search: keyword versus semantic

The original **Search saves** box retrieves ranked notes. Use **Ask your saves** for generated answers, comparisons, follow-up questions and notebook actions. It does not fabricate an itinerary when sources lack the details.

- **Unchecked Semantic search**: local BM25 retrieval with a small vocabulary mapping. No external model call. Conversational framing is removed and named topics must match together, so “cook paneer” cannot match an unrelated cooking video. Explicit “or” searches can match either topic. Original filenames are searchable too.
- **Checked Semantic search**: optional vector similarity combined with BM25 using Reciprocal Rank Fusion. Candidates are checked by the selected Gemini model for meaning, ordinary category relationships and paraphrases, without requiring shared words. A high cosine score alone is not accepted. This adds one generation request per semantic search. If the model check fails, the app clearly labels keyword fallback.
- New feed saves create their vector automatically using `gemini-embedding-001`. Existing legacy notes retain the optional indexing control under Note tools.
- Query embedding requires a key. If semantic access or vectors are unavailable, the interface reports the lexical fallback.
- Search covers prepared saved notes, not every frame of every raw feed clip. The coverage message shows how many saves are search-ready.
- The recipe-specific phrase "without an oven" applies an explicit source-evidence filter. Unknown equipment does not qualify as no-oven.

Example questions: "quiet beach", "beginner home workout", "macaroni cheese", "embeddings". Retrieval quality depends on whether that information is in the approved notes.

## Try it without a key

Choose **Explore demo notes**. The app adds clearly labelled synthetic text sources spanning food, travel, fitness and learning. These appear as draft notes in the saved grid and can be reviewed before search. They are not real videos and are never presented as analysed footage.

For your own text, choose **Add a save → Structured notes** and use:

```text
Title: A quiet beach
Category: travel
Key points:
The creator describes a quiet beach and a nearby cafe.
The creator suggests leaving the afternoon unplanned.
Tags:
beach, quiet, relaxed
Notes:
Location and opening hours are not stated.
```

This is a deterministic section parser, not an offline LLM. `Steps`, `Ingredients`, `Equipment` and `Entities` are also supported. Recipe ingredients use `name | quantity`; omitted quantities stay **Not stated**.

The `examples` folder contains a synthetic recipe screenshot and structured notes for image/food tests. The separately downloadable test-video bundle contains original Wikimedia clips and their attribution files.

## Runtime behaviour

- Source originals, thumbnails, notes and vectors live in `data/`. SQLite stores metadata and collections.
- Video thumbnails are captured by the browser from the actual saved video and cached locally. They do not call an AI model.
- One background worker bounds concurrent model calls. Retries are bounded and visible in traces.
- Partial or failed processing is shown explicitly, never represented as success.
- Unfinished media imports are marked as retryable failures after a restart. The separate agent chat and approval workflow uses persistent LangGraph checkpoints.
- Exact-note approval is fingerprint-bound. Editing after preview requires a fresh preview.
- Changed key points, steps and ingredients are labelled as reviewer edits and lose automatic source attribution. Original extraction is retained. **Reanalyse original** retains the prior note as a previous version and requires fresh review. Older notes with no retained evidence are flagged; they can be reanalysed with the corrected evidence-ID validator.
- The server binds to 127.0.0.1 and checks origins. This is a single-user local POC without multi-user authentication, not a public service.

## Architecture

```text
Upload / Save action
      |
Original media + collections in SQLite
      |
Optional background Gemini analysis OR structured-note parser
      |
Category + highlights + evidence + optional domain fields
      |
User review and exact-note approval
      |
BM25 + optional embeddings / RRF
      |
Ranked saved posts, playable sources and evidence
```

Full server: FastAPI with streamed agent progress. The original Python standard-library server remains available as a minimal baseline via `python3 app.py`; it does not serve the new agent API. UI: HTML/CSS/JavaScript. Storage: SQLite and local media files. API: Gemini REST with inline media and structured output, plus optional embeddings. Some internal API/storage fields retain the name `recipe` for backwards compatibility; the UI uses general saved notes.

## Deployment and operations

For a container deployment, start Docker and run:

```sh
docker compose up --build
```

Use http://127.0.0.1:8765 for Gather, http://127.0.0.1:3000 for the Grafana dashboard and http://127.0.0.1:9090/alerts for Prometheus alerts. Compose uses separate fresh Docker volumes; it does not automatically import this Mac's `data/` folder. The application and four MCP services, Qdrant, Prometheus and Grafana are configured together. Read MCP services mount source data read-only. The API invokes the write MCP server in process so approval capabilities never cross HTTP; the standalone action server denies writes without a grant.

Server keys can be supplied through environment variables or an untracked `.env` based on `.env.example`. Never share the filled file. `AGENT_MODEL` supplies an OpenRouter default; optional `GUARD_MODEL` enables a JSON-capable guard classifier. `RERANK_MODEL` controls local cross-encoder reranking. Configure provider access yourself; installation does not establish model quota.

Metrics are available at `/metrics`. Dashboard and alert configuration are in `ops/`; container startup and actual alert firing must be verified with Docker running. `ops/smoke_alert.py` can trigger three intentional no-key run errors in an isolated demo deployment.

## Verification

```sh
.venv/bin/python -m pytest tests -q
```

The tests use temporary data and mocked providers. They cover existing import/review/collection workflows plus the real LangGraph, local and remote MCP protocol, exact approval invalidation, restart review recovery, role budgets, source version checks, preference consent, frozen lessons, API streaming, origin checks and Qdrant filtering. Browser walkthroughs cover source playback, streamed cited excerpts, notebook approval/title edits, restored chats, preferences and responsive layouts.

See `VALIDATION.md` for tested behaviour and remaining limits. See `evaluation/README.md` for the labelled-data format, independent judge calibration, three-repeat baselines, red-team runner and signature switches. Synthetic fixtures are explicitly unreviewed; they do not establish real-video accuracy.

## Course-capstone scope

This is a working capstone prototype, with implemented orchestration, MCP, retrieval, approval, optional memory, development Reflexion tooling and deployment/evaluation setup. It is not a completed course submission. The team still needs representative human-reviewed cases, real-media timestamp labels, independent-judge calibration, live held-out comparisons, guard evaluation, measured costs, a verified container/alert demo and the final report/slides/recording.

Use `docs/GUIDE_CHECKLIST.md` to distinguish implementation from required evidence. Architecture, security and memory policies are documented in `docs/`. Direct Gemini media analysis and OpenRouter text agents are an explicit provider design choice to discuss with faculty. Instagram account access, scraping, Notion publishing, per-user authentication and production operation are outside the current scope.
