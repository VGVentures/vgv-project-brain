# Test Quality Review: Voyage.ai + Pinecone Migration

**Date**: 2026-04-09
**Reviewer**: Claude Opus 4.6 (automated)
**Scope**: 7 test files covering the Voyage.ai + Pinecone migration (32 total tests)

---

## Coverage Summary

- **Test run**: Could not execute (Bash denied) -- static review only
- **Files with tests**: 7/8 implementation files have corresponding test coverage
- **Total tests reviewed**: 32 across 7 test files

### Files Under Review

| Implementation File | Test File | Tests | Verdict |
|---|---|---|---|
| `src/vgv_rag/processing/embedder.py` | `tests/test_embedder.py` | 3 | Pass with issues |
| `src/vgv_rag/processing/reranker.py` | `tests/test_reranker.py` | 3 | Pass |
| `src/vgv_rag/storage/pinecone_store.py` | `tests/test_pinecone_store.py` | 7 | Pass with issues |
| `src/vgv_rag/storage/supabase_queries.py` | `tests/test_supabase_queries.py` | 7 | Pass with issues |
| `src/vgv_rag/server/tools/search.py` | `tests/test_search_tool.py` | 4 | Pass with issues |
| `src/vgv_rag/server/tools/ingest.py` + `list_sources.py` | `tests/test_tools.py` | 6 | Pass with issues |
| `src/vgv_rag/ingestion/scheduler.py` | `tests/test_scheduler.py` | 2 | Needs work |

### Missing Test Files

- `src/vgv_rag/processing/metadata.py` -- No corresponding test. `build_chunk_metadata` is a pure function with multiple fields to verify and is critical to search correctness.
- `src/vgv_rag/storage/client.py` -- No test for singleton client logic (low priority, 12 lines of glue).
- `src/vgv_rag/server/mcp_server.py` -- No integration test for MCP tool wiring (medium priority -- verifies tools are registered and route to handlers).

---

## Embedder Test Quality (`tests/test_embedder.py`)

**3 tests | Verdict: Pass with issues**

### Strengths
- Tests both `embed` (query path) and `embed_batch` (document path) -- verifying the critical `input_type` distinction between query and document embeddings
- Tests the empty-input fast path for `embed_batch`
- Uses `lru_cache.cache_clear()` correctly to prevent state leakage between tests

### Issues Found

1. **[Important] Missing error/retry behavior test**
   - The `embed` and `embed_batch` functions do not catch exceptions. If the Voyage.ai API fails, the error propagates unhandled. There is no test verifying what happens when `client.embed()` raises an exception. Either:
     - (a) Add a test proving the exception propagates (documenting this is intentional), or
     - (b) Add error handling to the implementation and test the fallback
   - Contrast: the reranker has a graceful fallback on failure, but the embedder does not. This asymmetry should be documented via tests.

2. **[Suggestion] Fixture duplicated between test files**
   - `mock_voyage` fixture is defined identically in both `test_embedder.py` and `test_reranker.py`. Should be extracted to `conftest.py` with a parameter or separate fixture names. Current duplication means a patch-target change requires editing two files.

3. **[Suggestion] No test for `asyncio.to_thread` wrapping**
   - The implementation wraps the synchronous Voyage client in `asyncio.to_thread`. This is important for concurrency but untested. A test that verifies the function is truly async-compatible (doesn't block the event loop) would add confidence.

---

## Reranker Test Quality (`tests/test_reranker.py`)

**3 tests | Verdict: Pass**

### Strengths
- Tests the happy path: reranking reorders documents by relevance score
- Tests graceful degradation: API failure returns original documents unchanged
- Tests `top_k` limiting behavior
- Asserts on `relevance_score` being added to the result dict -- good behavioral assertion

### Issues Found

1. **[Suggestion] No test for empty document list**
   - What happens when `rerank(query="test", documents=[], top_k=5)` is called? The implementation calls `client.rerank(documents=[], ...)`. Whether this should short-circuit or pass through to the API is worth documenting via a test.

---

## Pinecone Store Test Quality (`tests/test_pinecone_store.py`)

**7 tests | Verdict: Pass with issues**

### Strengths
- Good breadth: covers `upsert_vectors`, `query_vectors`, `delete_by_source`, `build_vector_id`, and `_translate_filters`
- Tests filter translation with multiple cases: None, empty dict, single filter, multiple filters
- Tests the "no vectors to delete" edge case correctly (verifies `delete` is not called)
- `build_vector_id` is a pure function tested without mocks -- good

### Issues Found

1. **[Critical] `query_vectors` test does not verify metadata extraction logic**
   - The implementation separates `content` from the rest of `metadata` (line 59 in pinecone_store.py: `{k: v for k, v in match.metadata.items() if k != "content"}`). The test mock returns `metadata={"content": "hello", "artifact_type": "prd"}`, then asserts `results[0]["content"] == "hello"` and `results[0]["score"] == 0.92`, but **never asserts that `results[0]["metadata"]` contains `{"artifact_type": "prd"}` with `content` excluded**. This is the central contract between Pinecone and the search tool -- the metadata reshaping logic is entirely untested.
   - **Fix**: Add `assert results[0]["metadata"] == {"artifact_type": "prd"}` and `assert "content" not in results[0]["metadata"]`.

2. **[Important] `verify_index` function is untested**
   - `verify_index()` (lines 81-89) is called during application startup. It returns `True`/`False` based on whether `describe_index_stats` succeeds. No test covers this. A failure here silently degrades the service at startup.
   - **Fix**: Add two tests: one for success and one for the exception path returning `False`.

3. **[Important] `upsert_vectors` test does not verify vector data is passed through**
   - The test calls `upsert_vectors` then asserts `mock_pinecone.upsert.assert_called_once()` and checks `namespace`. But it never asserts that the `vectors` parameter was actually passed through to `index.upsert(vectors=vectors, ...)`. If someone accidentally drops the vectors arg, this test still passes.
   - **Fix**: Assert `call_args.kwargs["vectors"] == vectors`.

4. **[Suggestion] No test for large batch behavior in `delete_by_source`**
   - `index.list` returns a paginated iterator. The test mocks a single page. Should also test multi-page iteration to ensure `all_ids.extend(page)` works across pages.

---

## Supabase Queries Test Quality (`tests/test_supabase_queries.py`)

**7 tests | Verdict: Pass with issues**

### Strengths
- All CRUD operations tested: upsert_project, upsert_source, update_source_sync_status, list_sources_for_project, get_project_by_name, list_projects_for_user
- Tests the "not found" case for `get_project_by_name`
- Good coverage of the data access layer

### Issues Found

1. **[Important] Tests are over-coupled to Supabase client chaining**
   - Every test mocks the deeply chained Supabase client pattern: `mock_supabase.table.return_value.upsert.return_value.select.return_value.execute.return_value`. This mirrors the implementation's method chain exactly. If Supabase SDK changes its chaining API, all tests break without any actual behavior change. This is implementation mirroring, not behavior testing.
   - **Mitigation**: This is somewhat unavoidable with the Supabase SDK, but tests should at least assert on what arguments are passed (e.g., the table name, the payload), not just the return value. Several tests only check the return value without verifying what was sent to the database.

2. **[Important] `update_source_sync_status` test has weak assertions**
   - The test only asserts `mock_supabase.table.assert_called_with("sources")`. It does not verify the payload passed to `.update()` -- specifically, it does not check:
     - The `sync_status` field is set to "success"
     - The `sync_error` field is set correctly
     - The `last_synced_at` field is set when status is "success" (the conditional logic on line 38-39 of supabase_queries.py)
   - This is the conditional logic in the implementation (`if status == "success": payload["last_synced_at"] = ...`) and it has zero test coverage.
   - **Fix**: Add assertions on the `.update()` call's payload. Add a second test case with `status="error"` to verify `last_synced_at` is NOT set.

3. **[Suggestion] No test for `list_sources_for_project` returning empty data**
   - The implementation has `return result.data or []` (line 50). The `or []` fallback for `None` data is untested.

4. **[Suggestion] `list_projects_for_user` test doesn't verify the Supabase join syntax**
   - The select call `"project_id, projects(*)"` is a Supabase-specific join. The test doesn't verify this select string is correct -- just that the return value is transformed. If someone changes the select to `"*"`, the test still passes.

---

## Search Tool Test Quality (`tests/test_search_tool.py`)

**4 tests | Verdict: Pass with issues**

### Strengths
- Tests the full search pipeline: embed -> query -> rerank -> format
- Tests authorization: user cannot search projects they are not a member of
- Tests the "no results" message
- Tests auto-detection of project from user membership

### Issues Found

1. **[Critical] `test_search_auto_detects_project` is a duplicate of `test_search_returns_formatted_chunks`**
   - Both tests call `handle_search_project_context(query="how does auth work", user_email="alice@verygood.ventures")` without specifying a project. Both assert `"PRD section about auth" in result`. They rely on the same autouse fixture and test the same code path. The second test adds no value.
   - **Fix**: Either (a) make `test_search_auto_detects_project` verify that `list_projects_for_user` was called (currently it doesn't), or (b) test a different scenario, such as a user with multiple projects.

2. **[Important] Autouse fixture masks per-test mock overrides**
   - The `mock_deps` fixture is `autouse=True` and sets up all dependencies. Then `test_search_returns_no_results_message` re-patches `query_vectors` and `rerank` inside the test body using `mocker.patch`. This creates a layered mocking situation where the autouse fixture runs first, then the per-test patches override. While this likely works with pytest-mock, it is fragile and confusing. If the autouse fixture changes, the per-test override might silently stop working.
   - **Fix**: Move shared setup to a non-autouse fixture and have each test opt in to the dependencies it needs, or use a parameterized fixture.

3. **[Important] No test for `filters` parameter**
   - The search tool accepts `filters={"artifact_type": "prd", "source_tool": "notion"}`. No test verifies that filters are passed through to `query_vectors`. The filter-building logic (lines 34-36 of search.py) strips falsy values -- this is untested.

4. **[Important] No test for `top_k` clamping**
   - The implementation clamps `top_k` to max 20 (`top_k = min(top_k, 20)`). No test verifies this boundary. A user passing `top_k=100` should still get at most 20 results.

5. **[Suggestion] Rerank candidate multiplier untested**
   - `RERANK_CANDIDATE_MULTIPLIER = 4` means the query requests `top_k * 4` candidates from Pinecone before reranking. No test verifies this multiplier is applied. If changed or removed, no test catches it.

---

## Tools Test Quality (`tests/test_tools.py`)

**6 tests | Verdict: Pass with issues**

### Strengths
- Tests both `list_sources` and `ingest_document` handlers
- Tests error paths: project not found, no content or URL provided
- Tests the happy path for ingestion: verifies chunk count in result message

### Issues Found

1. **[Important] `test_ingest_document_with_content` uses `patch()` context managers without `new_callable=AsyncMock`**
   - Lines 56-60 use `patch("...upsert_source", return_value="src-1")` etc. These are all async functions being patched with synchronous `MagicMock` objects (no `new_callable=AsyncMock`). In Python 3.12, `MagicMock` does handle `await` by returning the `return_value`, but this is an accidental behavior, not intentional. Using `AsyncMock` explicitly makes the test's intent clear and future-proof.
   - **Fix**: Use `new_callable=AsyncMock` for all patched async functions, or use `AsyncMock(return_value=...)` directly.

2. **[Important] No test for URL-based ingestion**
   - `handle_ingest_document` supports fetching content from a URL via `httpx.AsyncClient`. No test covers this path. The URL fetch logic (lines 27-33 in ingest.py) includes error handling for `HTTPError`, but this is entirely untested.
   - **Fix**: Add a test using `respx` (which is in dev dependencies) to mock the HTTP request.

3. **[Important] `list_sources` tests do not verify authorization**
   - The `handle_list_sources` function accepts `user_email` but the implementation does not check membership (unlike `handle_search_project_context`). This is either a bug in the implementation or the tests should document that authorization is not checked here. Either way, a test should cover this.

4. **[Suggestion] No test for `list_sources` without specifying a project**
   - The implementation has auto-detection logic (lines 12-17 in list_sources.py) that falls back to the user's first project. No test covers this path.

---

## Scheduler Test Quality (`tests/test_scheduler.py`)

**2 tests | Verdict: Needs work**

### Strengths
- Tests the core `sync_source` function, not the scheduler framework
- Tests both success (delete old + upsert new) and error (marks source as error) paths
- Verifies error message is passed through to `update_source_sync_status`

### Issues Found

1. **[Critical] Test asserts on keyword argument names that don't match the implementation**
   - `test_sync_source_deletes_old_and_upserts_new` (line 39) asserts:
     ```python
     delete_by_source.assert_called_once_with(namespace="proj-1", source_id="src-1")
     ```
   - The implementation calls (scheduler.py line 20):
     ```python
     await delete_by_source(namespace=source.project_id, source_id=source.id)
     ```
   - This looks correct at first glance, but the test also asserts on `upsert_vectors`:
     ```python
     call_kwargs = upsert_vectors.call_args.kwargs
     assert call_kwargs["namespace"] == "proj-1"
     ```
   - The implementation calls `upsert_vectors(namespace=source.project_id, vectors=vectors)`. The test does **not verify that vectors were constructed correctly** -- it only checks namespace. The entire chunking + embedding + metadata pipeline within `sync_source` is tested only by checking that upsert was called with the right namespace. The actual vectors content is unverified.

2. **[Important] No test for the `start_scheduler` function**
   - `start_scheduler` (lines 52-81) is the function that sets up APScheduler cron jobs and the `run_sync` inner function that iterates over projects and sources. This is untested. While unit-testing a scheduler is tricky, you could at minimum:
     - Verify `start_scheduler` returns a scheduler with the expected jobs
     - Verify `run_sync` calls `sync_source` for each discovered source
   - Without this, there's no test proving the scheduler actually wires sources to `sync_source`.

3. **[Important] No test for multiple documents in a single sync**
   - `sync_source` iterates over `docs` (line 22-35). The test provides exactly one document. There's no test for multiple documents, which would exercise the loop and verify vector IDs don't collide.

4. **[Suggestion] `is_business_hours` is untested**
   - While trivial, it contains logic (weekday + hour check) that could regress. A quick parameterized test would cover it.

---

## Anti-Patterns Found

### 1. [test_search_tool.py] Duplicate test masquerading as different scenario
- **Issue**: `test_search_auto_detects_project` and `test_search_returns_formatted_chunks` execute the same code path with the same inputs and the same assertions.
- **Fix**: Give `test_search_auto_detects_project` distinct assertions -- verify that `get_project_by_name` was NOT called, and that `list_projects_for_user` WAS called.

### 2. [test_tools.py:56-60] Synchronous mocks for async functions
- **Issue**: `patch("...upsert_source", return_value="src-1")` patches async functions with synchronous MagicMock.
- **Fix**: Use `AsyncMock(return_value="src-1")` or `new_callable=AsyncMock`.

### 3. [test_supabase_queries.py] Implementation mirroring in Supabase chain mocking
- **Issue**: Tests reproduce the exact Supabase client method chain (`table().upsert().select().execute()`). Refactoring the chain breaks tests without changing behavior.
- **Mitigation**: Acceptable for a thin data access layer, but add payload assertions to make the tests more behavioral.

### 4. [test_search_tool.py] Autouse fixture with per-test overrides
- **Issue**: Global autouse fixture combined with per-test `mocker.patch` creates implicit test dependencies.
- **Fix**: Use explicit fixtures or parameterization.

### 5. [test_embedder.py, test_reranker.py] Duplicated fixture definitions
- **Issue**: The `mock_voyage` fixture is copy-pasted between two files.
- **Fix**: Move to `conftest.py` as two separate fixtures (`mock_voyage_embedder`, `mock_voyage_reranker`) or a parameterized factory.

---

## Recommendations (Priority Order)

1. **[Critical] Fix `test_search_auto_detects_project` -- currently a duplicate test providing false coverage signal.** Either add assertions that prove auto-detection works (verify `list_projects_for_user` was called, `get_project_by_name` was NOT called), or replace with a multi-project scenario test.

2. **[Critical] Add metadata extraction assertion to `test_query_vectors`.** The content/metadata split is the core contract between Pinecone and the search layer. Currently untested.

3. **[Critical] Verify `sync_source` constructs vectors correctly.** The scheduler test only checks that `upsert_vectors` was called with the right namespace. Add assertions on the vectors' structure (id format, metadata fields, embedding values).

4. **[Important] Add `verify_index` tests.** This runs at startup and determines service health. Two tests: success case and exception case.

5. **[Important] Add tests for `update_source_sync_status` conditional logic.** The `last_synced_at` is only set on success -- this branching logic has zero coverage.

6. **[Important] Add filter passthrough test for search tool.** The filter-building logic strips falsy values and is untested.

7. **[Important] Add URL-based ingestion test using `respx`.** The HTTP fetch path in `handle_ingest_document` is entirely uncovered despite `respx` being in dev dependencies.

8. **[Important] Use `AsyncMock` consistently for patched async functions in `test_tools.py`.**

9. **[Suggestion] Extract duplicate `mock_voyage` fixture to `conftest.py`.**

10. **[Suggestion] Add test for `metadata.py:build_chunk_metadata`.** Pure function, easy to test, critical to search quality.

---

## Verdict

**Fix 8 issues before merging.**

The migration test suite covers the basic happy paths for all major components and demonstrates good awareness of failure modes (reranker fallback, empty inputs, project-not-found). However, there are three critical gaps: a duplicate test inflating coverage, missing assertions on Pinecone's metadata extraction contract, and insufficient verification of the scheduler's vector construction pipeline. The important issues (missing `verify_index` tests, untested conditional logic in sync status, missing filter/URL tests) represent real risk areas where bugs could ship undetected. The codebase's testing framework choices (pytest-asyncio, pytest-mock, respx) are appropriate and consistently applied, but `AsyncMock` usage should be standardized.
