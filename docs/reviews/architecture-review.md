# Architecture Review: Voyage.ai + Pinecone Migration

**Date**: 2026-04-09
**Reviewer**: Architecture Review Agent
**Scope**: Migration from local sentence-transformers + Supabase pgvector to Voyage.ai cloud embeddings + Pinecone serverless vector DB

---

## Architecture Overview

The migration restructured the storage and embedding layers:

- **Before**: Local MiniLM-L6 embeddings (384-dim) stored in Supabase pgvector with RLS-based access control
- **After**: Voyage.ai cloud embeddings (voyage-4-lite, 1024-dim) stored in Pinecone (namespace=project_id), with Supabase retaining auth + relational metadata only

### New Data Flow

- **Ingestion**: Text -> `embedder.embed_batch()` (input_type=document) -> `pinecone_store.upsert_vectors()` (namespace=project_id)
- **Query**: Text -> `embedder.embed()` (input_type=query) -> `pinecone_store.query_vectors()` (namespace) -> `reranker.rerank()` -> formatted results
- **Auth/Metadata**: Supabase retains `projects`, `sources`, `project_members` tables; `chunks` table dropped via migration 002

---

## Layer Separation

### Identified Layers

| Layer | Modules |
|---|---|
| **Config** | `config/settings.py` |
| **Ingestion** | `ingestion/connectors/*.py`, `ingestion/scheduler.py`, `ingestion/project_hub_parser.py` |
| **Processing** | `processing/embedder.py`, `processing/reranker.py`, `processing/chunker.py`, `processing/metadata.py` |
| **Storage** | `storage/client.py`, `storage/supabase_queries.py`, `storage/pinecone_store.py`, `storage/migrate.py` |
| **Server/Presentation** | `server/mcp_server.py`, `server/auth.py`, `server/tools/*.py` |

### Layer Dependency Analysis

**Violations found: 1**

1. `src/vgv_rag/ingestion/scheduler.py:53` -- The `start_scheduler()` function directly imports and calls `get_client()` from `storage/client.py` to execute a raw Supabase table query (`client.table("projects").select("id").execute()`). This bypasses the `supabase_queries.py` abstraction entirely. All other modules correctly route through `supabase_queries.py` for Supabase access. The scheduler should use a query function from `supabase_queries.py` (e.g., a `list_all_projects()` function) rather than reaching directly into the storage client.

**Clean files**: All other source files maintain correct dependency direction:
- Server tools depend on processing + storage (correct)
- Ingestion connectors depend only on their own types (correct)
- Processing modules are standalone (correct)
- Storage modules depend only on config (correct)

---

## State Management Assessment

This is a backend service, so "state management" maps to how runtime state is initialized, cached, and shared across the application.

### Singleton/Client Management

- **Supabase client** (`storage/client.py`): Module-level global `_client` with lazy init via `get_client()`. Correct pattern for a backend service.
- **Pinecone index** (`storage/pinecone_store.py`): Module-level `_index = None` plus `@lru_cache(maxsize=1)` on `_get_index()`. The global `_index` variable is declared but never used -- `_get_index()` uses `lru_cache` for caching. The dead variable is harmless but confusing.
- **Voyage.ai clients** (`processing/embedder.py`, `processing/reranker.py`): Both use `@lru_cache(maxsize=1)` on `_get_client()`. Correct.
- **Settings** (`config/settings.py`): Module-level `settings = Settings()` singleton. Correct, but note that the singleton is instantiated at import time, which means importing the module before `load_dotenv()` in `main.py:run()` would yield empty/default values. Currently this is handled by lazy imports inside functions (e.g., `_get_index()` imports `settings` inside the function body), but this is fragile.

### Assessment Summary

- **Singleton pattern**: Consistent use of lazy singletons with `lru_cache` -- clean.
- **Settings lifecycle**: Fragile. The `Settings()` singleton at module level in `config/settings.py` is constructed at import time. The `load_dotenv()` call in `main.py:run()` must happen before any other module imports `settings`. This works today due to deferred imports, but any refactoring that triggers an eager import of `settings` before `load_dotenv()` will silently produce empty config values.
- **Scheduler state**: `start_scheduler()` captures `get_connector` via closure, which is clean.

---

## Dependency Direction

### Cross-Package Dependencies

**Direction violations: 1**

1. **Scheduler bypasses storage abstraction**: `ingestion/scheduler.py:53` imports `storage.client.get_client` and directly queries `client.table("projects")`. All other modules correctly use `storage/supabase_queries.py` as the abstraction boundary. This creates a hidden coupling between the ingestion layer and the raw Supabase client, making it harder to swap the relational store or mock in tests.

**Clean dependencies:**
- `server/tools/search.py` -> `processing/embedder`, `processing/reranker`, `storage/supabase_queries`, `storage/pinecone_store` (correct)
- `server/tools/ingest.py` -> `processing/embedder`, `processing/chunker`, `processing/metadata`, `storage/supabase_queries`, `storage/pinecone_store`, `ingestion/connectors/types` (correct)
- `server/tools/list_sources.py` -> `storage/supabase_queries` (correct)
- `ingestion/scheduler.py` -> `storage/supabase_queries`, `storage/pinecone_store`, `processing/chunker`, `processing/embedder`, `processing/metadata`, `ingestion/connectors/types` (correct, except the raw client import noted above)
- `main.py` -> `server/mcp_server`, `ingestion/scheduler`, `config/settings`, all connectors (correct for composition root)

### Circular Dependencies

None detected. All dependency arrows flow from server -> processing/storage -> config.

---

## Security and Authorization

### Critical: RLS Removed, Application-Level Authorization Incomplete

**Severity: CRITICAL**

The original architecture used PostgreSQL Row Level Security on the `chunks` table to ensure users could only query their own projects' data. Migration 002 removes this table and its RLS policies. The replacement is application-level membership checking in `server/tools/search.py`.

**What is in place:**
- `search.py:29-31`: After resolving the project, the handler calls `list_projects_for_user(user_email)` and verifies the `project_id` is in the returned list.
- The membership check is correct in logic.

**What is missing or weak:**

1. **`ingest_document` has NO authorization check** (`server/tools/ingest.py`): The `handle_ingest_document()` function accepts a project name, looks it up, and directly ingests content. There is no `user_email` parameter, no membership verification. Any authenticated user (or the hardcoded `DEV_EMAIL`) can ingest into any project. This is a critical gap -- it allows content injection into projects the user does not belong to.

2. **`list_sources` has NO authorization check** (`server/tools/list_sources.py`): The `handle_list_sources()` function accepts a project name and user_email but does not verify that the user is a member of the requested project when a project name is explicitly provided (lines 7-10). It only auto-selects from the user's projects when no project name is given.

3. **Auth is not wired to MCP tools** (`server/mcp_server.py:9`): The `DEV_EMAIL` hardcode means all requests bypass real authentication. This is explicitly marked as a TODO, but it means the membership checks in `search.py` are effectively testing against a hardcoded email, not a real JWT-derived identity. Until this is resolved, all authorization is theater.

4. **No authorization on Pinecone operations**: Pinecone namespaces use `project_id` as the namespace key. If an attacker (or buggy code) constructs a `query_vectors()` call with an arbitrary namespace, Pinecone will return results. The authorization boundary depends entirely on the application layer checking membership before calling Pinecone -- there is no database-level enforcement like RLS provided.

### Comparison to Original Design

The CLAUDE.md spec explicitly states: "Row Level Security in PostgreSQL ensures that even a bug in the service layer can't leak cross-project data. The database enforces the boundary." The migration removes this guarantee and replaces it with application-level checks that are inconsistently applied. This is the single most important architectural regression in the migration.

---

## Embedding Dimension Mismatch with Documentation

**Severity: IMPORTANT**

- The CLAUDE.md spec documents `all-MiniLM-L6-v2` producing `VECTOR(384)` dimensions
- Migration 001 creates `chunks.embedding VECTOR(384)`
- The actual embedder (`processing/embedder.py`) uses `voyage-4-lite`, which produces 1024-dimensional vectors
- Migration 002 drops the chunks table entirely, so there is no dimension conflict in the database itself
- However, the CLAUDE.md documentation has not been updated to reflect the new embedding model or dimensions

This is not a runtime bug, but the documentation is misleading. Anyone reading the CLAUDE.md will believe the system uses local MiniLM embeddings and pgvector.

---

## Docker Compose Port Mismatch

**Severity: IMPORTANT**

- `docker-compose.yml` maps ports `3002:3002`
- `Dockerfile` exposes port `3000`
- `config/settings.py` defaults `port` to `3000`
- `Dockerfile` healthcheck hits `localhost:3000`
- `docker-compose.yml` healthcheck also hits `localhost:3000`

The port mapping `3002:3002` in docker-compose does not match the application's default port of `3000`. The service will listen on port 3000 inside the container, but docker-compose maps host port 3002 to container port 3002 (which nothing is listening on). The health check will pass (it runs inside the container on port 3000), but external access on port 3002 will fail.

The mapping should be `3002:3000` (host:container) or `3000:3000`.

---

## Sync Scheduler: Full Delete + Re-insert on Every Sync

**Severity: IMPORTANT**

`ingestion/scheduler.py:20-21`:
```python
docs = await connector.fetch_documents(source, source.last_synced_at)
await delete_by_source(namespace=source.project_id, source_id=source.id)
```

On every sync cycle, the scheduler:
1. Fetches documents modified since `last_synced_at` (incremental)
2. Deletes ALL vectors for the source from Pinecone (full delete)
3. Re-inserts only the newly fetched documents

This means that on an incremental sync, all previously indexed documents for the source are deleted, and only the documents modified since the last sync are re-inserted. Unchanged documents are lost. This is a data loss bug.

The correct pattern is either:
- **Full resync**: Fetch ALL documents (not just since `last_synced_at`), delete all, re-insert all
- **Incremental**: Fetch only changed documents, delete only their vectors, insert new vectors

The current implementation mixes incremental fetch with full delete, which will progressively lose data on each sync cycle.

---

## Pinecone Delete-by-Source Implementation

**Severity: SUGGESTION**

`storage/pinecone_store.py:66-78`:
```python
async def delete_by_source(namespace: str, source_id: str) -> None:
    index = _get_index()
    all_ids = []
    for page in await asyncio.to_thread(
        lambda: index.list(prefix=f"{source_id}:", namespace=namespace)
    ):
        all_ids.extend(page)
    if all_ids:
        await asyncio.to_thread(
            lambda: index.delete(ids=all_ids, namespace=namespace)
        )
```

The `index.list()` call returns a paginated iterator, but the entire iteration is wrapped in a single `asyncio.to_thread()` call. If there are many vectors (thousands), this will block the thread pool worker for the entire pagination. Consider iterating pages and yielding control between pages, or using Pinecone's `delete(filter=...)` with a metadata filter for `source_id` instead of listing then deleting.

---

## Reranker Graceful Degradation

**Severity: CLEAN**

`processing/reranker.py:24-36` correctly wraps the rerank call in a try/except and falls back to returning the original results (truncated to `top_k`) if the Voyage.ai reranker fails. This is good defensive design for an external API dependency.

---

## Metadata Storage in Pinecone

**Severity: SUGGESTION**

`processing/metadata.py:8-14` stores full chunk `content` as a Pinecone metadata field. This is then retrieved in `pinecone_store.py:58` via `match.metadata.get("content", "")`. While this works, it means every vector in Pinecone carries the full text of its chunk as metadata. Pinecone charges for metadata storage and has metadata size limits (40KB per vector for serverless). For large chunks, this could hit the limit. Consider whether a reference-based approach (store content in Supabase, reference by ID from Pinecone) would be more cost-effective at scale.

---

## Package Structure

### `vgv_rag` (main package)

- [x] Dependency manifest exists (`pyproject.toml`) with proper name and dependencies
- [x] Test directory exists with comprehensive test files
- [x] Clear responsibility: MCP RAG service
- [x] Business logic separated from server/tool handlers

### Sub-package Assessment

| Package | Verdict | Notes |
|---|---|---|
| `config/` | Complete | Single settings file, clean |
| `ingestion/connectors/` | Complete | Each connector is a separate module with shared types |
| `processing/` | Complete | Embedder, reranker, chunker, metadata all separate |
| `storage/` | Complete | Clean split between Supabase (relational) and Pinecone (vector) |
| `server/tools/` | Complete | One handler per MCP tool |
| `server/` | Complete | MCP server + auth module |

### Missing Items

- No linting configuration (no `ruff.toml`, `.flake8`, or `[tool.ruff]` in `pyproject.toml`). For a VGV project, a linter should be configured.
- No type checking configuration (`mypy.ini` or `[tool.mypy]`). The codebase uses type hints extensively but has no enforcement.

---

## CLAUDE.md Documentation Drift

**Severity: IMPORTANT**

The CLAUDE.md is significantly out of date with the actual implementation:

1. **Tech stack table** still lists `@xenova/transformers (all-MiniLM-L6-v2)` for embeddings and `Supabase (PostgreSQL + pgvector)` for vector DB. The actual stack is Voyage.ai + Pinecone.
2. **Language** is listed as TypeScript/Node.js. The actual implementation is Python.
3. **Project structure** shows a TypeScript layout (`src/*.ts` files). The actual structure is Python (`src/vgv_rag/*.py`).
4. **Connector contracts** show TypeScript interfaces. The actual contracts are Python Protocol classes.
5. **Deployment section** references Node.js Docker image and npm. The actual deployment uses Python 3.12 + uv.
6. **Key Design Decisions** section states "TypeScript, not Python" and "Supabase, not a dedicated vector DB" -- both of which have been reversed.
7. The architecture diagram still shows `Embedding Engine (MiniLM-L6)` as a component.

The CLAUDE.md appears to be the original planning document that was never updated after the migration to Python + Voyage.ai + Pinecone. This creates a significant risk: anyone (human or AI) reading the CLAUDE.md will have a fundamentally incorrect mental model of the system.

---

## Verdict

### Fix 3 critical/important violations before merging:

| # | Severity | Issue | Location |
|---|---|---|---|
| 1 | **Critical** | `ingest_document` tool has no authorization check; any user can inject content into any project | `src/vgv_rag/server/tools/ingest.py` |
| 2 | **Critical** | `list_sources` tool does not verify project membership when a project name is explicitly provided | `src/vgv_rag/server/tools/list_sources.py:7-10` |
| 3 | **Critical** | Incremental sync deletes ALL vectors for a source but only re-inserts recently modified documents, causing progressive data loss | `src/vgv_rag/ingestion/scheduler.py:20-21` |
| 4 | **Important** | Docker Compose port mapping `3002:3002` does not match the application's port `3000` | `docker-compose.yml:5` |
| 5 | **Important** | CLAUDE.md documents an entirely different tech stack (TypeScript, MiniLM, pgvector) than what is implemented (Python, Voyage.ai, Pinecone) | `CLAUDE.md` |
| 6 | **Important** | Scheduler bypasses `supabase_queries.py` abstraction and queries Supabase client directly | `src/vgv_rag/ingestion/scheduler.py:53-58` |
| 7 | **Suggestion** | `pinecone_store.py:10` declares unused `_index = None` global variable | `src/vgv_rag/storage/pinecone_store.py:10` |
| 8 | **Suggestion** | Full chunk content stored in Pinecone metadata may hit 40KB per-vector limit at scale | `src/vgv_rag/processing/metadata.py:13` |
| 9 | **Suggestion** | `delete_by_source` lists all vector IDs in a single blocking thread call; consider batching or filter-based delete | `src/vgv_rag/storage/pinecone_store.py:66-78` |
| 10 | **Suggestion** | No linting or type-checking configuration in `pyproject.toml` | `pyproject.toml` |
| 11 | **Suggestion** | `Settings()` singleton instantiated at import time creates fragile init ordering with `load_dotenv()` | `src/vgv_rag/config/settings.py:36` |

**Architecture status: Needs work. Fix the 3 critical issues (authorization gaps and data-loss sync bug) and the 3 important issues before merging.**
