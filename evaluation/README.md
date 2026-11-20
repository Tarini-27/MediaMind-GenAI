# Evaluation and honest reporting

Fixtures: 20 development + 40 held-out tasks, grouped by 12 source scenarios. Every variant of one scenario is in one split. These are synthetic source passages, not human-validated clips. They are a harness starting point, not a completed golden benchmark. The application and its MCP tools cannot read these files.

The team must review labels, replace/extend fixtures with representative real videos, record consent/licensing and independently mark timestamps. Add negative/ambiguous examples and realistic caption/audio disagreements. Do not tune agents on held-out queries. The author of these AI-generated fixtures cannot provide the independent team separation the guide requires.

Run from the project folder with its environment active:

```sh
python evaluation/run.py --split dev --repeats 1 --workflow team
python evaluation/run.py --split heldout --repeats 3 --output evaluation/results/retrieval-before.json
python evaluation/run.py --split heldout --repeats 3 --rerank --output evaluation/results/retrieval-after.json
```

The last command enables the configured `RERANK_MODEL`; export it first. A warning means reranking was not exercised. Model weights download on first use. Semantic evaluation requires `--live --semantic --model YOUR_GEMINI_MODEL` plus `GEMINI_API_KEY`, and embeds the isolated fixture notes before querying. This consumes quota. The vectors represent source notes, not raw frames.

For live E1, run fixed/single/team with the same provider, model, cases, tool limits and model-call budget. All three use the same evidence corpus, filters and citation checker. Fixed returns source excerpts, single uses one ReAct role, team uses specialist roles. Model-call counts differ and are reported. The supervisor rewrite applies to single/team; describe this in the report. This is a pragmatic baseline, not evidence that multiple agents are better.

```sh
python evaluation/run.py --split heldout --repeats 3 --live --provider openrouter --model PROVIDER/MODEL --judge OTHER_PROVIDER/MODEL --workflow team --output evaluation/results/team.json
```

The independent judge is optional in smoke runs; it is required for semantic correctness claims. Without it, workflow success means an expected citation was returned, not that the answer was correct. Errors/timeouts stay in the denominator. Price is reported only when supplied by the provider; unavailable cost is null. Extraction cost, embedding cost and reflection cost must be measured separately and included in the final report.

E2: `python evaluation/redteam.py` runs 30 attacks through user queries, provided text and visible-text evidence plus 20 clean cases, with defenses off/on. Add `--live --model MODEL` to exercise an LLM. The result is a marker-based smoke metric, not a proof of security. Human review and independent judging remain required.

E3: use development failures with `python -m capstone.reflexion reflect RECORD.json --model PROVIDER/MODEL`, inspect with `list`, then `review ID --decision approve|reject --reason '...'`. Never auto-approve lessons. `freeze` returns an immutable playbook version. Export its approved lesson list as `{"lessons":[...]}` and pass `--playbook FILE.json` to compare with/without it. Keep one justified rejected lesson in evidence. Held-out records cannot generate lessons. Include reflection generation/review cost; do not edit frozen files between comparison runs.

E4: compare `--modality transcript` and `--modality multimodal`, and `--verify` / `--no-verify`. The current fixture ablation compares evidence channels; it does not run separate audio-only and multimodal extraction models. For the final signature result, build both indexes from the same real clips and score timestamp error against human annotations.

Memory: `--memory` enables preferences. To demonstrate a meaningful effect, seed consented preference cases in a dedicated evaluation dataset; the default synthetic fixtures contain no user preferences, so an on/off difference would not be meaningful.

Judge calibration: replace all 20 null pairs in `calibration-template.jsonl` with actual independently supplied human judgements and judge outputs. `python evaluation/calibrate.py FILE.jsonl` refuses blank/incomplete labels and reports Cohen's kappa.

The CI gate is a small development retrieval regression check. It does not replace any course experiment. Record all runs, settings, prompt version, playbook version, failures, limits and interpretation in the final team-authored report.
