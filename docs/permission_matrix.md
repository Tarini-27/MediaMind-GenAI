# Permission matrix (source of truth: `config/mediamind.yaml`)

Role 4 owns this. Everyone adds their tool/agent here as they build; a test fails if any non-organizer agent gets a write tool.

| Agent | Tools it may call | Read/Write |
|---|---|---|
| Reader | media.ocr, media.caption, media.transcribe | read |
| Classifier | rules.get_schema | read |
| Extractor | rules.get_schema, rules.validate, rules.normalize_units | read |
| Critic | rules.validate | read |
| Answerer | knowledge.search, knowledge.get_record, knowledge.list_collections | read |
| Organizer | library.save, library.update, library.move, library.collect, library.soft_delete, rules.dedupe | **write, behind approval gate** |

Enforced by `control/hooks.py::call_tool`: permission check, `user_id` injected by the hook (never from the model), per-run call budget, write tools require an approved proposal.

## TODO (Role 4)
- [ ] Threat model one-pager (`docs/threat_model.md`): assets, attackers, entry points incl. text inside screenshots, which layer stops each
- [ ] Wire `ApprovalGate` into LangGraph `interrupt()` with Role 3 (pair for 1 hour in week 2)
- [ ] Prompt Guard 2 / Llama Guard 4 as extra layers behind `detect_injection(classifier=...)`
- [ ] Langfuse tracing in the post-tool hook
- [ ] Grafana dashboard + one alert; CI eval gate; clean-machine install check
