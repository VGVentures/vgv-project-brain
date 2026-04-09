# PR Readiness Review: Voyage.ai + Pinecone Migration

**Branch:** `worktree-feat+google-drive-connector`
**Reviewer:** Automated Code Review Agent
**Date:** 2026-04-09
**Tests:** 80/80 passing

---

## Executive Summary

This branch implements a migration from local sentence-transformers + Supabase pgvector to Voyage.ai embeddings + Pinecone vector storage, with Voyage.ai reranking added. The core migration is clean and well-structured across 11 commits. All 80 tests pass. However, the README.md is severely outdated, the docker-compose.yml has a port mismatch, and the CLAUDE.md Implementation Order section contains stale TypeScript-era references.

---

## 1. Tests

**Status: PASS -- all 80 tests pass in 1.20s**

Test coverage includes:
- `test_pinecone_store.py` (7 tests) -- upsert, query, filter translation, delete, verify
- `test_reranker.py` (3 tests) -- reranking, fallback on failure, top_k
- `test_embedder.py` (3 tests) -- query embedding, batch embedding, empty batch
- `test_supabase_queries.py` (7 tests) -- all CRUD operations
- `test_search_tool.py` (4 tests) -- search, no results, non-member rejection, auto-detect
- `test_scheduler.py` (2 tests) -- sync deletes+upserts, error handling
- Connector tests (24 tests total across all 6 connectors)
- Hub parser, chunker, settings, tools, auth tests

The old `tests/test_storage.py` has been properly deleted. No dangling imports to removed modules exist in `src/` or `tests/`.

---

## 2. Critical Issues

### 2.1 [Critical] docker-compose.yml port mismatch

**File:** `/docker-compose.yml` (line 5)

The docker-compose maps port `3002:3002` but the application listens on port 3000 (hardcoded in `main.py`, Dockerfile EXPOSE, and the healthcheck). The healthcheck itself checks `localhost:3000`, which means:
- External traffic on port 3002 will not reach the app on port 3000
- The healthcheck will work because it runs inside the container on port 3000

This was likely a leftover from a previous edit. It should be `3000:3000` (or `3002:3000` if external port 3002 is intentional, but that conflicts with the CLAUDE.md docs).

### 2.2 [Critical] README.md not updated for the migration

**File:** `/README.md`

The README contains multiple stale references that will confuse any developer onboarding:

- Line 3: "indexes...into Supabase pgvector" -- should mention Pinecone
- Line 48: "creates the...chunks...tables, enables the pgvector extension, creates the HNSW index" -- chunks table is removed in migration 002
- Line 112: "The sentence-transformer model (~90MB) is downloaded on first run and cached in a named volume" -- sentence-transformers removed; Voyage.ai is a cloud API
- Line 122: `queries.py` listed in project structure -- file renamed to `supabase_queries.py`
- Line 124: `embedder.py # sentence-transformers all-MiniLM-L6-v2` -- now uses Voyage.ai
- Missing: No mention of `VOYAGE_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` in the setup table
- Missing: No mention of Google Drive connector, `GOOGLE_SERVICE_ACCOUNT_JSON`
- Missing: No mention of `pinecone_store.py`, `reranker.py`, `supabase_queries.py` in project structure

---

## 3. Important Issues

### 3.1 [Important] CLAUDE.md Implementation Order section has stale TypeScript references

**File:** `/CLAUDE.md` (lines 538-571)

The "Implementation Order" section still references:
- Line 543: `package.json`, `tsconfig.json` -- this is a Python project using `pyproject.toml`
- Line 546: `@xenova/transformers` wrapper that returns "384-dim vector" -- now Voyage.ai returning 1024-dim
- Line 556: `seed-project.ts` -- actual file is `seed_project.py`

While the core architecture sections of CLAUDE.md were updated correctly (tech stack, project structure, query flow, key design decisions), this historical section was missed.

### 3.2 [Important] CLAUDE.md Connector Details uses TypeScript/npm library names

**File:** `/CLAUDE.md` (lines 298-316)

The connector descriptions reference TypeScript libraries that are not used:
- Line 299: `@notionhq/client` -- actual dependency is `notion-client` (Python)
- Line 305: `@slack/web-api` -- actual dependency is `slack-sdk` (Python)
- Line 312: `@octokit/rest` -- actual dependency is `PyGithub` (Python)

### 3.3 [Important] CLAUDE.md Onboarding section references `npx ts-node`

**File:** `/CLAUDE.md` (line 502)

The onboarding command says:
```
npx ts-node scripts/seed-project.ts
```
But the actual command is:
```
uv run python scripts/seed_project.py
```

### 3.4 [Important] CLAUDE.md line 532 says "scoped via RLS" but RLS no longer applies

**File:** `/CLAUDE.md` (line 532)

In the "Onboarding a User" section, step 5 says "Queries are automatically scoped to the user's projects via RLS." However, since vectors are now in Pinecone (not Supabase), RLS does not apply to search results. This is correctly noted in the Key Design Decisions section (line 577), but the user-facing onboarding section contradicts it.

### 3.5 [Important] Connector contracts section uses TypeScript interface syntax

**File:** `/CLAUDE.md` (lines 276-294)

The connector contract is written as a TypeScript interface, but the actual codebase uses Python `Protocol` classes defined in `src/vgv_rag/ingestion/connectors/types.py`. This is misleading for developers referencing the spec.

### 3.6 [Important] Chunking config section uses TypeScript syntax

**File:** `/CLAUDE.md` (lines 340-383)

The chunking strategy is documented in TypeScript object notation, while the actual implementation is Python dataclasses in `chunker.py`.

### 3.7 [Important] `voyage_api_key` and `pinecone_api_key` default to empty string, not marked required

**File:** `/src/vgv_rag/config/settings.py` (lines 24, 27)

Both settings default to `""` with a comment saying "startup health check fails if empty." However, pydantic-settings will happily start with empty strings. The startup check in `main.py` only calls `verify_index()` which catches connection errors, but an empty API key passed to Voyage.ai would fail at first embed call, not at startup. Consider making these fields `str` without defaults (truly required) or adding explicit validation.

---

## 4. Suggestions

### 4.1 [Suggestion] Brainstorm document deleted from this branch

The file `docs/brainstorm/2026-04-09-google-drive-connector-brainstorm-doc.md` is being deleted in this diff. If this was intentional (moved or superseded by the plan doc), that is fine. If accidental, it should be restored.

### 4.2 [Suggestion] `001_initial_schema.sql` still creates the chunks table + pgvector extension

**File:** `/src/vgv_rag/storage/migrations/001_initial_schema.sql`

The initial migration still creates the `chunks` table, `vector` extension, HNSW index, RLS policy, and `match_chunks` function -- all of which are immediately removed by `002_remove_chunks.sql`. For a fresh deployment, running both migrations creates then drops these objects. Consider consolidating into a single migration that only creates what is needed now (projects, sources, project_members). This avoids confusion and the unnecessary `CREATE EXTENSION vector` which requires superuser in some Supabase configurations.

### 4.3 [Suggestion] TODO in `mcp_server.py` references "Task 20"

**File:** `/src/vgv_rag/server/mcp_server.py` (line 9)

```python
# TODO(Task 20): replace with JWT-derived email once auth is wired
DEV_EMAIL = "dev@verygood.ventures"
```

This is a known pre-existing placeholder for auth wiring. It is not a regression from this PR. However, it should be noted that all MCP tool calls currently bypass auth and use a hardcoded email.

### 4.4 [Suggestion] `_get_index` and `_get_client` use `lru_cache` for singletons

**Files:** `/src/vgv_rag/storage/pinecone_store.py`, `/src/vgv_rag/processing/embedder.py`, `/src/vgv_rag/processing/reranker.py`

Using `lru_cache` for singleton initialization is functional, but means these clients cannot be reconfigured or reset without calling `cache_clear()` (which the tests do correctly). An alternative would be a simple module-level variable with a `get_or_create` pattern, which is slightly more explicit. Low priority.

### 4.5 [Suggestion] `delete_by_source` pagination may not work as expected with Pinecone SDK

**File:** `/src/vgv_rag/storage/pinecone_store.py` (lines 66-78)

The `index.list()` call returns a generator of pages. The current code iterates with `for page in await asyncio.to_thread(...)`, but `asyncio.to_thread` will consume the entire generator since `list()` returns a lazy iterator. This works but may have unexpected behavior if the list is very large. The test mocks pass, so this is not blocking.

### 4.6 [Suggestion] Metadata `date` field stored as integer timestamp

**File:** `/src/vgv_rag/processing/metadata.py` (line 11)

The date is stored as `int(doc.date.timestamp())` (Unix epoch seconds). This is fine for Pinecone metadata filtering, but loses timezone info and is less human-readable in debug output. Consider storing as ISO-8601 string if Pinecone metadata filtering supports string comparison for dates.

---

## 5. What Was Done Well

- **Clean separation of concerns:** Supabase for relational data, Pinecone for vectors. The `supabase_queries.py` / `pinecone_store.py` split is clear.
- **Reranking with graceful fallback:** The reranker catches all exceptions and falls back to the original order. This is defensive and production-ready.
- **Comprehensive test coverage:** 80 tests covering all new modules (pinecone_store, reranker, embedder, supabase_queries) plus updated tests for search and scheduler.
- **Security-conscious search:** The search handler verifies project membership at the application layer before querying Pinecone, correctly compensating for the loss of RLS.
- **Voyage.ai asymmetric encoding:** Using `input_type="query"` for search and `input_type="document"` for ingestion is best practice for Voyage.ai.
- **Migration path provided:** `002_remove_chunks.sql` provides a clean migration for existing deployments.
- **Commit history is logical and incremental:** Each commit has a clear scope and message.

---

## 6. Commit History Review

The 11 commits on top of the Google Drive branch are clean and logical:

1. `79ba40e` -- dependency swap in pyproject.toml
2. `ca6264a` -- supabase_queries.py extracted from queries.py
3. `f4cb832` -- embedder rewritten for Voyage.ai
4. `a2ffabe` -- reranker added
5. `2bbb63b` -- Pinecone store added
6. `dad568a` -- metadata builder updated, migration 002 added
7. `0f61b22` -- search tool rewritten
8. `d387d60` -- ingest tool rewritten
9. `b2e57ac` -- scheduler updated
10. `2253a56` -- Dockerfile simplified
11. `6d8de53` -- CLAUDE.md updated

No merge commits, no fixup noise. The progression makes logical sense for code review.

---

## 7. Security Check

- No secrets or credentials found in committed files
- `.env` is in `.gitignore`
- API keys are read from environment variables via pydantic-settings
- `.env.example` contains only placeholder values (e.g., `pa-...`, `pcsk_...`)
- Service account JSON is either a file path or base64-encoded, never hardcoded

---

## 8. Deleted Files Verification

| File | Status |
|------|--------|
| `src/vgv_rag/storage/queries.py` | Properly deleted, renamed to `supabase_queries.py` |
| `tests/test_storage.py` | Properly deleted, replaced by `test_supabase_queries.py` + `test_pinecone_store.py` |
| No dangling imports to old modules in `src/` | Verified |
| No dangling imports to old modules in `tests/` | Verified |
| References in `docs/plans/` | Still reference old `queries.py` but these are historical planning docs, not runtime code |

---

## Summary

| Category | Count |
|----------|-------|
| Critical | 2 |
| Important | 7 |
| Suggestions | 6 |

The core migration code is solid and well-tested. The blocking issues are the docker-compose port mismatch and the README.md being completely outdated for the new architecture. The CLAUDE.md issues are important but less urgent since it is a spec document being incrementally updated.
