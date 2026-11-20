# Validation — agentic Gather upgrade

Verified locally on 3 November 2026.

- 56 tests pass: the original 27 workflow tests plus 29 additional search/agent/backend tests. Provider generation is mocked; graph execution, MCP protocol and local Qdrant are real.
- Browser walkthrough: streamed source excerpts, citation opening, exact-note approval, title edit and new approval, notebook write, restored conversation, opt-in preferences, deletion and responsive layout. No live generation calls were made.
- Browser video test: an actual local Wikimedia clip opens at an authored 00:05 QA annotation. This tests seeking, not model timestamp accuracy.
- Cross-encoder weights downloaded and exercised with real inference. Synthetic development retrieval completed with/without reranking; this is a harness smoke result, not evidence of a quality improvement.
- Qdrant test verifies vectors from sources outside the current live source set cannot enter results.
- A real HTTP FastMCP read server was started and queried in the integration test.
- A paused approval survived graph/checkpointer reconstruction. Old hashes and changed/deleted sources cannot publish a notebook note.
- Synthetic red-team mechanics: 30 attacks and 20 clean cases each with defenses off/on. No-key outputs test routing/controls only; zero marker successes are not a security result.
- Docker Compose configuration parses. Docker's daemon was not running, so a container build/start, Grafana dashboard and fired Prometheus alert have not been verified. The alert smoke script is provided for a running deployment.
- All media/notes/collections present at upgrade were preserved; a SQLite backup was made before starting the new app. No live key from conversation history was used.

## Accuracy and course evidence still pending

Live multimodal extraction, generated conversation/comparison quality, long-term preference usefulness, guard classifier performance, independent judge calibration and held-out experimental comparisons still require real runs. Synthetic fixtures are unreviewed. Obtain human labels and faculty agreement on signature challenges. An agent's own verifier does not establish semantic truth.

Approximate model timestamps are not word-aligned transcripts. Cross-encoder first use loads model weights and can take several seconds. Semantic vectors must be built for approved sources; otherwise the UI reports fallback. Gemini media/embeddings and the selected text-agent provider require available quota.

Conversation checkpoints can retain prior evidence and preferences until **New chat** deletes that chat. Read the memory policy before a pilot. The app has no multi-user authentication and must remain local.

Full mappings and limitations are in `docs/GUIDE_CHECKLIST.md`, `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md` and `docs/MEMORY_POLICY.md`. Evaluation instructions are in `evaluation/README.md`.

## Search relevance correction

Fixed semantic search admitting every source above a loose cosine cutoff. Cosine/RRF now select candidates; vector-only results need a cross-encoder relevance verdict. Strong direct keyword matches are retained. Without a working checker, unchecked vector candidates are excluded and keyword fallback is disclosed. Keywords retain all named topics rather than matching any one broad word. Search loading/failure clears old cards; only explicit Clear restores the full library.

Browser reproduction used the user's three actual indexed sources in an isolated local copy: **cat door → cat only**; **quantum physics**, **dogs at the door**, and **cook paneer → no matches**; **potato tortilla → tortilla only**; **macaroni cheese → pasta only**; **food → the two food videos**. Query embedding was stubbed to admit all three vector candidates; existing stored source vectors and actual local cross-encoder inference were used. This isolates the reported relevance bug without a paid/provider call. Live query embedding access was not re-tested. A simulated HTTP failure also left zero result cards, and Clear restored all three.

The default zero-logit cutoff is specific to the shipped ms-marco reranker, not a probability guarantee. Calibrate it on independently labelled queries for the capstone evaluation.

## Broader concepts and paraphrases

The previous small cross-encoder was reproduced locally rejecting `animal`, `pet animal` and `an animal opening the entrance` for the cat save, despite admitting `cat door`. Its hard score gate has been replaced with a generative source-relevance check. The query words need not occur in the note. Positive IDs must belong to the candidate set and include a supporting quote actually present in that candidate. The selected UI model is forwarded to the search endpoint. In agent search, this check uses the run's model and budget. The small cross-encoder can reorder accepted passages but cannot veto conceptual matches.

Three added regression tests exercise broader concepts with zero lexical overlap, validate quoted support and reject invented IDs/quotes, and verify explicit fallback on provider failure. Provider responses are mocked for these tests; live Gemini generalization has not been evaluated because no server-side key is configured. The previous real cross-encoder/browser reproduction describes the superseded cutoff implementation, not a live result for the new model check. One extra generation request is used per semantic query.

Browser integration checked conceptual results with a mocked generation provider and stubbed query embeddings against an isolated copy of the three existing saves; `animal`, `pet animal` and `an animal opening the entrance` preserved the provider's cat decision with no animal keyword overlap. An unrelated dog query was excluded, and removing the connection visibly labelled keyword fallback. This verifies wiring, not live Gemini accuracy. Candidate selection now takes the top indexed vectors without an arbitrary cosine acceptance cutoff; the source-relevance decision is responsible for final inclusion. No media or indexes were rebuilt.
