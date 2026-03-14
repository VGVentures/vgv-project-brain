import pytest


@pytest.fixture(autouse=True)
def mock_deps(mocker):
    mocker.patch("vgv_rag.server.tools.search.search_chunks", return_value=[
        {
            "id": "1",
            "content": "PRD section about auth",
            "metadata": {
                "source_tool": "notion",
                "artifact_type": "prd",
                "source_url": "https://notion.so/123",
            },
            "similarity": 0.92,
        },
    ])
    mocker.patch("vgv_rag.server.tools.search.list_projects_for_user", return_value=[
        {"id": "proj-1", "name": "TestProject"}
    ])
    mocker.patch("vgv_rag.server.tools.search.get_project_by_name", return_value={
        "id": "proj-1", "name": "TestProject"
    })
    mocker.patch("vgv_rag.server.tools.search.embed", return_value=[0.1] * 384)


@pytest.mark.asyncio
async def test_search_returns_formatted_chunks():
    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="how does auth work",
        user_email="alice@verygood.ventures",
    )

    assert "PRD section about auth" in result
    assert "notion.so/123" in result
    assert "92%" in result


@pytest.mark.asyncio
async def test_search_returns_no_results_message(mocker):
    mocker.patch("vgv_rag.server.tools.search.search_chunks", return_value=[])

    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="something obscure",
        user_email="alice@verygood.ventures",
    )
    assert "No relevant results" in result
