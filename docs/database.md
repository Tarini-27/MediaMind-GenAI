# Database

SQLite, one file: `data/mediamind.sqlite` (override with `MEDIAMIND_DB`). Created automatically on first start.
Code: `src/mediamind/db.py` (schema, connection, seed), `api/store.py` (records), `control/repos.py` (approvals).

```bash
python scripts/init_db.py            # create tables, seed demo data if empty
python scripts/init_db.py --reset    # delete the file first, recreate and reseed
MEDIAMIND_SEED=0 ...                 # skip demo seed (e.g. when loading your own corpus)
```

## Tables

| Table | Holds | Notes |
|---|---|---|
| `users` | one row per user id | created on first save |
| `items` | approved, saved records | `user_id` on every row; `kind` is image or video and `thumb` names a video's thumbnail; `deleted_at` set = soft-deleted; `fields` is JSON for schema-guided extraction; `text` is the OCR/transcript/caption source used for citations; `confidence` is the classifier score |
| `collections`, `item_collections` | user collections | reserved for `library.move` (Organizer); not used by the UI yet |
| `proposals` | the approval queue | payload (JSON), status, `approved_hash`; persisted so a restart loses no pending approval and never replays an executed one |

## Rules everyone follows
1. **Every query filters by `user_id`.** No exceptions, including retrieval. The vector index (Chroma) is filtered the same way.
2. **Writes go through the approval gate.** `store.save_item` and `store.soft_delete` are only called from `ApprovalGate.execute()`.
3. **Soft delete only.** Hard deletes need a separate, approved action.
4. **`get_item` treats soft-deleted rows as absent**, so the citation check rejects them.
5. **Tests use a temporary database** (`tests/conftest.py`), never `data/mediamind.sqlite`.

## What stays stable (the contract)
`get_item`, `list_items`, `search`, `save_item`, `soft_delete` in `api/store.py`; record keys
`id, user_id, media, kind, thumb, category, title, tags, text, fields, confidence, created_at`.

## Not here yet
- Vector index and BM25 index (Role 2).
- LangGraph checkpointer and long-term memory store (separate SQLite files, Role 3).
- Evaluation cases (golden and held-out sets live as files under `data/`, not in this DB; held-out stays git-ignored).
- A migration tool. `init_db()` adds the `thumb` column to older databases automatically; anything bigger means `--reset` for now.
