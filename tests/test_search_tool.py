import pytest
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def mock_deps(mocker):
    mocker.patch("vgv_rag.server.tools.search.query_vectors", new_callable=AsyncMock, return_value=[
        {
            "content": "PRD section about auth",
            "metadata": {
                "source_tool": "notion",
                "artifact_type": "prd",
                "source_url": "https://notion.so/123",
            },
            "score": 0.92,
        },
    ])
    mocker.patch("vgv_rag.server.tools.search.list_projects_for_user", new_callable=AsyncMock, return_value=[
        {"id": "proj-1", "name": "TestProject"}
    ])
    mocker.patch("vgv_rag.server.tools.search.get_project_by_name", new_callable=AsyncMock, return_value={
        "id": "proj-1", "name": "TestProject"
    })
    mocker.patch("vgv_rag.server.tools.search.get_project_by_id", new_callable=AsyncMock, return_value={
        "id": "proj-1", "name": "TestProject", "program_id": None
    })
    mocker.patch("vgv_rag.server.tools.search.list_programs_for_user", new_callable=AsyncMock, return_value=[])
    mocker.patch("vgv_rag.server.tools.search.embed", new_callable=AsyncMock, return_value=[0.1] * 1024)
    mocker.patch("vgv_rag.server.tools.search.rerank", new_callable=AsyncMock, side_effect=lambda q, docs, top_k: docs[:top_k])


@pytest.mark.asyncio
async def test_search_returns_formatted_chunks():
    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="how does auth work",
        user_email="alice@verygood.ventures",
    )

    assert "PRD section about auth" in result
    assert "notion.so/123" in result


@pytest.mark.asyncio
async def test_search_returns_no_results_message(mocker):
    mocker.patch("vgv_rag.server.tools.search.query_vectors", new_callable=AsyncMock, return_value=[])
    mocker.patch("vgv_rag.server.tools.search.rerank", new_callable=AsyncMock, return_value=[])

    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="something obscure",
        user_email="alice@verygood.ventures",
    )
    assert "No relevant results" in result


@pytest.mark.asyncio
async def test_search_rejects_non_member(mocker):
    """User cannot search projects they are not a member of."""
    mocker.patch("vgv_rag.server.tools.search.get_project_by_name", new_callable=AsyncMock, return_value={"id": "proj-secret"})
    mocker.patch("vgv_rag.server.tools.search.list_projects_for_user", new_callable=AsyncMock, return_value=[
        {"id": "proj-mine"}  # Different project
    ])

    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="secrets", user_email="alice@verygood.ventures", project="SecretProject"
    )
    assert "not a member" in result.lower() or "not authorized" in result.lower()


@pytest.mark.asyncio
async def test_search_auto_detects_project_and_queries_correct_namespace(mocker):
    """When no project is specified, auto-detect and query the correct Pinecone namespace."""
    from vgv_rag.server.tools.search import handle_search_project_context, query_vectors

    await handle_search_project_context(
        query="how does auth work",
        user_email="alice@verygood.ventures",
    )

    # Should query with the auto-detected project's ID as namespace
    call_kwargs = query_vectors.call_args.kwargs
    assert call_kwargs["namespace"] == "proj-1"


@pytest.mark.asyncio
async def test_search_includes_program_namespace(mocker):
    """When project has a parent program, search both project and program namespaces."""
    mocker.patch("vgv_rag.server.tools.search.get_project_by_id", new_callable=AsyncMock, return_value={
        "id": "proj-1", "name": "TestProject", "program_id": "prog-1"
    })
    mocker.patch("vgv_rag.server.tools.search.query_vectors", new_callable=AsyncMock, return_value=[
        {"content": "result", "metadata": {"source_tool": "notion"}, "score": 0.9},
    ])

    from vgv_rag.server.tools.search import handle_search_project_context, query_vectors

    await handle_search_project_context(
        query="program-level content",
        user_email="alice@verygood.ventures",
        project="TestProject",
    )

    # Should have queried both project and program namespaces
    namespaces_queried = [call.kwargs["namespace"] for call in query_vectors.call_args_list]
    assert "proj-1" in namespaces_queried
    assert "prog-1" in namespaces_queried


@pytest.mark.asyncio
async def test_search_non_member_cannot_access_program_content(mocker):
    """User who is NOT a member of any child project cannot search program content."""
    mocker.patch("vgv_rag.server.tools.search.get_project_by_name", new_callable=AsyncMock, return_value={"id": "proj-other"})
    mocker.patch("vgv_rag.server.tools.search.list_projects_for_user", new_callable=AsyncMock, return_value=[
        {"id": "proj-mine"}
    ])

    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="program secrets", user_email="alice@verygood.ventures", project="OtherProject"
    )
    assert "not authorized" in result.lower()


@pytest.mark.asyncio
async def test_search_continues_on_partial_namespace_failure(mocker):
    """If one namespace fails, results from other namespaces are still returned."""
    mocker.patch("vgv_rag.server.tools.search.get_project_by_id", new_callable=AsyncMock, return_value={
        "id": "proj-1", "name": "TestProject", "program_id": "prog-1"
    })

    call_count = 0

    async def mock_query_vectors(**kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs["namespace"] == "prog-1":
            raise RuntimeError("Pinecone timeout")
        return [{"content": "project result", "metadata": {"source_tool": "notion"}, "score": 0.9}]

    mocker.patch("vgv_rag.server.tools.search.query_vectors", side_effect=mock_query_vectors)

    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="test query",
        user_email="alice@verygood.ventures",
        project="TestProject",
    )
    assert "project result" in result
