# Course checklist — implementation vs evidence

The main interface is Feed → Save to a collection → automatic extraction/evidence checks/embedding → Search ready. Internal private indexing does not pause for a second approval. AI-generated notes are labelled separately from human-reviewed notes. Agent notebook writes still require exact-payload approval through `interrupt()`. Course/operations tools are separate from this everyday flow.

Read this alongside the faculty guide. “Implemented” never means an experiment has been completed. This checklist is deliberately candid.

| Guide area | Current implementation | What the team still must demonstrate |
|---|---|---|
| Domain and two signature challenges | Media evidence retrieval; grounded answers with missing information | Faculty agreement; real clips with speech/visual differences and independent timestamp labels |
| Retrieval | Evidence passage IDs, source/date metadata; BM25; optional note vectors/RRF/Qdrant; cross-encoder; model query rewrite | Label 30+ representative retrieval queries; report before/after Recall@5; verify active reranker/embedding modes |
| FastMCP | Four typed servers: media-tools, knowledge-search, validation-engine, notes-actions; structured errors and permission hooks | Live remote read-server demo and per-tool tests; explain in-process write capabilities |
| LangGraph | Typed state, conditional paths, one repair loop, durable SQLite checkpoints, persistent approval interrupt | Restart/pause demo and failure recovery traces |
| Planning and ReAct | Visible model-generated constrained plan, query decomposition, specialist tool-observation loops and repair; single-agent ReAct baseline | Show live plans and tool traces; confirm faculty accepts bounded loops and a constrained routing graph |
| Multi-agent baseline | Supervisor plus retrieval/writer/verifier roles; fixed/single/team harness, shared limits/models | Same-budget held-out three-repeat comparisons; cost/benefit evidence, not just role names |
| Memory | Working context trimmed to six messages; SQLite-backed LangGraph Store; opt-in preferences and policy | Context summarization if needed; meaningful memory on/off cases; validate retention/deletion limitations |
| Reflexion | Dev-only proposal -> human approve/reject -> applicable lesson retrieval -> frozen snapshots | Real development failures, reviewed/rejected lessons, held-out before/after comparison incl reflection cost |
| Golden evaluation | 60 synthetic fixtures grouped 20 dev/40 held-out; isolated evaluator, metrics and failure accounting | Human review and realistic negative/ambiguous cases; member separation and no tuning on held-out labels |
| Independent judge | Other-family guard; judge invocation and 20-pair calibration template; Cohen kappa calculation | Supply actual human labels and run/calibrate independent judge; no scores are fabricated |
| Security | Local boundary, key isolation, role allow-lists, output scrubbing, gated writes, budgets, heuristic injection filtering | Configure/test optional OpenRouter guard classifier, add realistic multimodal red-team attacks and defenses-off/on metrics; false blocks |
| Human control | Exact payload approval/edit/reject via interrupt, one-use grants, source version recheck, idempotent mock notebook write | Demonstrate changed payload and removed source failing approval |
| API/deployment | FastAPI event streaming, Compose app/MCP/Qdrant/Prometheus/Grafana, dashboard/alert configuration | Successful clean Docker startup and fired alert; images/config validated separately from an actual run |
| Operations/CI | Reported token/cost fields, latency/tool metrics, dependency locks and CI regression gate | Provider-complete cost incl extraction/reflection/embedding; executed CI history; optional richer tracing |
| Required experiments | Runner supports E1 baseline, E2 attacks/clean, E3 playbook, E4 evidence/verification switches | All final comparisons repeated three times, held-out tables, human interpretation and failure examples |
| Submission | README, architecture walkthrough, threat/memory policies, evaluator and checklist | Team-authored final 4–6-page report, experiment/contribution logs, slides and backup recording |

Exact team roles from the guide: Product and evaluation lead; Knowledge, memory and tools engineer; Agents and orchestration engineer; Control, security and deployment engineer. Evaluation ownership must be independent of the person tuning agents/defenses as the guide specifies.

Do not present synthetic smoke results or mocked-provider tests as real-video accuracy. Do not claim all requirements are complete while the evidence and the explicit gaps above remain.
