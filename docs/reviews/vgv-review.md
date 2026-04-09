## VGV Code Review

### Summary

This migration replaces local sentence-transformers embeddings and Supabase pgvector with Voyage.ai cloud embeddings and Pinecone serverless vector storage. The architectural direction is sound: it eliminates the heavy torch dependency, shrinks the Docker image, and gains asymmetric query/document embeddings plus reranking. Layer separation is clean, test coverage exists for all new modules, and the migration is well-decomposed across commits. However, there are several issues that need attention before merge: a security gap in `list_sources` (no membership verification), a port mismatch in `docker-compose.yml`, missing Pinecone batch-size limits on upserts, the `.gitignore` accidentally drops `.DS_Store` and `.claude/` exclusions, and the `search.py` tool makes a redundant `list_projects_for_user` call. With these fixes, the migration is ready to merge.

---

### Critical -- Must Fix Before Merge

- **`src/vgv_rag/server/tools/list_sources.py` (entire file)** -- No membership verification before returning sources.
  - Why: `handle_list_sources` resolves the project by name and returns its sources without checking whether `user_email` is a member of that project. The `search.py` handler correctly calls `list_projects_for_user` and verifies membership, but `list_sources.py` does not. This lets any authenticated user enumerate sources of any project by guessing its name. This is an access-control regression -- the pre-migration `search` handler enforced membership via RLS on the `chunks` table, but now that enforcement is gone for the `list_sources` tool.
  - Fix: Add the same membership check used in `search.py`:
    ```python
    user_projects = await list_projects_for_user(user_email)
    if project_id not in [p["id"] for p in user_projects]:
        return "Not authorized: you are not a member of this project."
    ```

- **`docker-compose.yml:6`** -- Port mapping `3002:3002` does not match the application port `3000`.
  - Why: The app defaults to port 3000 (in `settings.py` and `Dockerfile`), and the healthcheck inside `docker-compose.yml` curls `localhost:3000`. But the port mapping publishes `3002:3002`, meaning the container port 3002 is forwarded but the app listens on 3000. The service will be unreachable from the host, and the healthcheck will fail because it checks port 3000 inside the container (which is correct) but traffic from outside never reaches port 3000.
  - Fix: Change to `"3000:3000"` (or `"3002:3000"` if you want the host port to be 3002).

- **`.gitignore`** -- Accidentally removed `.DS_Store` and `.claude/` entries.
  - Why: The diff shows these two lines were deleted. `.DS_Store` files will now be committed, and any `.claude/` metadata could leak into the repo. This is a regression introduced in this branch, not an intentional change.
  - Fix: Re-add both lines:
    ```
    .DS_Store
    .claude/
    ```

---

### Important -- Should Fix

- **`src/vgv_rag/storage/pinecone_store.py:30-34`** -- No batch-size limit on `upsert_vectors`.
  - Why: Pinecone's upsert API has a limit of 100 vectors per request (or 2MB per request). If a large document produces hundreds of chunks, the upsert will fail with an API error. The scheduler calls `upsert_vectors` per document, but a single document can easily exceed 100 chunks (e.g., a long PRD or meeting transcript).
  - Fix: Batch the vectors into groups of 100:
    ```python
    UPSERT_BATCH_SIZE = 100

    async def upsert_vectors(namespace: str, vectors: list[dict]) -> None:
        index = _get_index()
        for i in range(0, len(vectors), UPSERT_BATCH_SIZE):
            batch = vectors[i : i + UPSERT_BATCH_SIZE]
            await asyncio.to_thread(
                lambda b=batch: index.upsert(vectors=b, namespace=namespace)
            )
    ```

- **`src/vgv_rag/processing/embedder.py:25-35`** -- No batch-size limit on `embed_batch`.
  - Why: Voyage.ai's embed API has a limit of 128 texts per request. The `embed_batch` function passes the entire `texts` list in a single call. If a large document produces more than 128 chunks, the API call will fail.
  - Fix: Split into sub-batches of 128:
    ```python
    EMBED_BATCH_SIZE = 128

    async def embed_batch(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = _get_client()
        all_embeddings = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            result = await asyncio.to_thread(
                lambda b=batch: client.embed(texts=b, model=MODEL, input_type="document")
            )
            all_embeddings.extend(result.embeddings)
        return all_embeddings
    ```

- **`src/vgv_rag/server/tools/search.py:23-30`** -- Double call to `list_projects_for_user`.
  - Why: When a project name is provided, the function calls `get_project_by_name` to resolve the ID, then calls `list_projects_for_user` to verify membership. But when no project name is provided, it also calls `list_projects_for_user` to auto-detect -- and then calls it again on line 29 for the membership check. This is a redundant database query on every auto-detected search.
  - Fix: Cache the first call result and reuse it:
    ```python
    user_projects = await list_projects_for_user(user_email)

    if project:
        proj = await get_project_by_name(project)
        if not proj:
            return f"Project not found: {project}"
        project_id = proj["id"]
    else:
        if not user_projects:
            return "No projects found for your account."
        project_id = user_projects[0]["id"]

    if project_id not in [p["id"] for p in user_projects]:
        return "Not authorized: you are not a member of this project."
    ```

- **`src/vgv_rag/storage/pinecone_store.py:66-78`** -- `delete_by_source` pagination logic is incorrect.
  - Why: The `index.list()` method returns a paginated iterator, but the code wraps the entire call in `asyncio.to_thread` and then iterates over the result synchronously. The `for page in ...` loop consumes the iterator inside the `to_thread` call, but the code structure suggests it expects to iterate outside. The actual behavior depends on whether `index.list()` returns an eager list or a lazy iterator. If it returns a lazy iterator that makes additional API calls, those calls happen on the main thread, not the background thread. Additionally, the inner `page` variable contains the vector IDs directly from the list response -- the double-list `[["src-1:0", "src-1:1"]]` structure in the test mock may not match the actual Pinecone SDK response format.
  - Fix: Collect all IDs inside the `to_thread` block:
    ```python
    async def delete_by_source(namespace: str, source_id: str) -> None:
        index = _get_index()

        def _collect_ids():
            all_ids = []
            for page in index.list(prefix=f"{source_id}:", namespace=namespace):
                all_ids.extend(page)
            return all_ids

        all_ids = await asyncio.to_thread(_collect_ids)

        if all_ids:
            await asyncio.to_thread(
                lambda: index.delete(ids=all_ids, namespace=namespace)
            )
    ```

- **`src/vgv_rag/processing/metadata.py:11`** -- Date stored as Unix timestamp integer loses timezone and readability.
  - Why: The previous implementation stored `doc.date.isoformat()` as a string. The new version stores `int(doc.date.timestamp())`. While Pinecone metadata supports numeric filtering (which is useful for `before`/`after` filters), the search tool formats the date back to the user as a raw integer (line 69 of `search.py`: `lines.append(f"Date: {meta['date']}")`), producing output like `Date: 1712678400` instead of a human-readable date. The `before`/`after` filter parameters in the MCP tool schema accept ISO date strings, but the filter translation in `_translate_filters` just does `$eq` -- it does not convert ISO dates to timestamps for range queries.
  - Fix: Either (a) store dates as ISO strings and handle range filtering with Pinecone's `$gte`/`$lte` operators (requires parsing in the filter builder), or (b) keep the integer but convert it back to ISO format for display in `search.py` and implement proper range-filter translation.

- **`src/vgv_rag/config/settings.py:24,28`** -- `voyage_api_key` and `pinecone_api_key` default to empty strings instead of being required.
  - Why: These are described in comments as "Required" but have empty-string defaults, meaning the app will start without them and only fail later at runtime when the first embed or query is attempted. The startup health check (`verify_index`) will catch the Pinecone case, but there is no corresponding health check for Voyage.ai. An empty Voyage API key will produce a confusing error from the Voyage client.
  - Fix: Either remove the defaults (making them truly required by Pydantic, which will fail at startup with a clear error), or add a Voyage.ai health check in `on_startup` that validates the key is set and the API is reachable.

- **`src/vgv_rag/storage/pinecone_store.py:10`** -- Module-level mutable global `_index = None` alongside `@lru_cache`.
  - Why: The `_index` global is declared but never used -- `_get_index()` uses `@lru_cache` for singleton behavior. The unused global is dead code that creates confusion about which caching mechanism is in effect.
  - Fix: Remove line 10 (`_index = None`).

- **`src/vgv_rag/ingestion/scheduler.py:20`** -- `delete_by_source` is called unconditionally before upserting, even for incremental syncs.
  - Why: The scheduler fetches documents modified since `last_synced_at` (incremental), but then deletes ALL vectors for that source before re-inserting. This means during a sync cycle, there is a window where the source has zero vectors in Pinecone. For frequently syncing sources, this creates intermittent search gaps. The old pgvector approach had the same pattern, but with Pinecone's eventual consistency, the window is wider.
  - Fix: Use Pinecone's upsert semantics (which overwrite by ID) and only delete vectors whose source documents are no longer present. Or, move to a "delete then upsert" per-document rather than per-source.

- **`src/vgv_rag/ingestion/scheduler.py:29`** -- Vector IDs will collide across documents within the same source.
  - Why: `build_vector_id(source.id, i)` uses the chunk index `i` within each document, but `i` resets to 0 for each document in the loop. If a source has two documents with 3 chunks each, the vectors will be `src:0, src:1, src:2` for doc 1, and `src:0, src:1, src:2` for doc 2 -- overwriting the first document's vectors. Only the last document's chunks survive.
  - Fix: Use a running counter across all documents for the source, or include the document identifier in the vector ID:
    ```python
    chunk_offset = 0
    for doc in docs:
        chunks = chunk(doc.content, doc.artifact_type)
        if not chunks:
            continue
        embeddings = await embed_batch(chunks)
        vectors = [
            {
                "id": build_vector_id(source.id, chunk_offset + i),
                "values": embeddings[i],
                "metadata": build_chunk_metadata(doc, i, text),
            }
            for i, text in enumerate(chunks)
        ]
        await upsert_vectors(namespace=source.project_id, vectors=vectors)
        chunk_offset += len(chunks)
    ```

---

### Suggestions -- Nice to Have

- **`src/vgv_rag/storage/pinecone_store.py:56-63`** -- Content stored in Pinecone metadata has no size guard.
  - Suggestion: Pinecone metadata has a 40KB limit per vector. If chunk content approaches this limit, upserts will fail silently or error. Consider truncating content or storing it separately (e.g., in Supabase) and only putting a reference in Pinecone metadata.

- **`src/vgv_rag/processing/reranker.py:22`** -- Assumes all documents have a `"content"` key.
  - Suggestion: Add a defensive check or use `.get("content", "")` to avoid a `KeyError` if a malformed document reaches the reranker.

- **`src/vgv_rag/storage/migrations/001_initial_schema.sql`** -- Still creates the `chunks` table and `pgvector` extension.
  - Suggestion: Since `002_remove_chunks.sql` immediately drops these, consider updating `001_initial_schema.sql` to not create them in the first place, so new deployments don't create and immediately drop a table. Alternatively, consolidate into a single migration.

- **`tests/test_search_tool.py`** -- Missing test for the `filters` parameter being passed through to `query_vectors`.
  - Suggestion: Add a test that provides `filters={"artifact_type": "prd"}` and verifies `query_vectors` receives the filter.

- **`tests/test_pinecone_store.py:73-79`** -- `test_delete_by_source_no_vectors` asserts delete is not called, but the mock returns `[[]]` (a list containing an empty list).
  - Suggestion: The `all_ids.extend(page)` on an empty list produces no IDs, so the test passes, but the mock structure `[[]]` vs `[]` is confusing. Align the mock with the actual SDK response shape.

- **`src/vgv_rag/server/tools/search.py:61`** -- Relevance score formatting assumes 0-1 range.
  - Suggestion: Pinecone cosine similarity scores are in [0, 1], but the reranker relevance scores may differ. The `score * 100` formatting works for both, but the label "relevance" is misleading when displaying the raw Pinecone score (which is similarity, not relevance). Consider labeling appropriately based on whether reranking occurred.

- **`src/vgv_rag/server/tools/ingest.py:28`** -- HTTP timeout of 10 seconds may be too short for large documents.
  - Suggestion: Consider increasing to 30 seconds, or making it configurable.

- **General** -- No rate-limit handling for Voyage.ai or Pinecone API calls.
  - Suggestion: Both services have rate limits. Consider adding retry-with-backoff logic, especially in the scheduler which may process many documents in a single sync cycle.

---

### Simplicity Assessment

- **Lines that could be removed**: ~5 (the unused `_index = None` global, the redundant `list_projects_for_user` call in search.py)
- **Unnecessary abstractions**: None -- the code is appropriately minimal. Each module has a single clear responsibility.
- **YAGNI violations**: None detected. The migration adds only what is needed for the Voyage.ai + Pinecone integration.
- **Complexity verdict**: Minor tweaks needed. The codebase is lean and well-factored. The main complexity issue is the vector ID collision bug in the scheduler, which is a correctness problem rather than an over-engineering problem.

---

### Testing Assessment

- **New code with tests**: Partial coverage.
  - `embedder.py` -- Covered (3 tests: query type, batch type, empty batch)
  - `reranker.py` -- Covered (3 tests: sorted results, fallback on failure, top_k)
  - `pinecone_store.py` -- Covered (6 tests: upsert, query, filters, delete, delete-no-vectors, build_vector_id, translate_filters)
  - `supabase_queries.py` -- Covered (6 tests: upsert project, upsert source, update status, list sources, get project, list user projects)
  - `search.py` -- Covered (4 tests: formatted output, no results, non-member rejection, auto-detect)
  - `ingest.py` -- Covered in `test_tools.py` (3 tests: no content, not found, with content)
  - Missing: No test for the scheduler's vector ID collision (which would catch the bug). No test for `metadata.py` changes. No test for `list_sources` membership bypass.
- **Test quality**: Meaningful. Tests verify behavior (state transitions, error handling, access control), not just that functions don't throw. Mock setup is clean and consistent. The `lru_cache.cache_clear()` in fixtures is good practice.
- **State management test coverage**: N/A (no state management layer in this project).
- **UI component test coverage**: N/A (no UI in this project).
- **Missing edge cases**:
  - Scheduler: multiple documents per source (would catch the ID collision bug)
  - `embed_batch`: large lists exceeding Voyage.ai batch limits
  - `upsert_vectors`: large vectors lists exceeding Pinecone batch limits
  - `list_sources`: unauthorized access to another project's sources
  - `metadata.py`: `build_chunk_metadata` with None author, date formatting
