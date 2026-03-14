import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_supabase(mocker):
    mock = MagicMock()
    mocker.patch("vgv_rag.storage.queries.get_client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_insert_chunks_calls_supabase(mock_supabase):
    from vgv_rag.storage.queries import insert_chunks

    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}], error=None)

    await insert_chunks([{
        "project_id": "proj-1",
        "source_id": "src-1",
        "content": "hello",
        "embedding": [0.0] * 384,
        "metadata": {"artifact_type": "prd"},
    }])

    mock_supabase.table.assert_called_with("chunks")


@pytest.mark.asyncio
async def test_search_chunks_calls_rpc(mock_supabase):
    from vgv_rag.storage.queries import search_chunks

    mock_supabase.rpc.return_value.execute.return_value = MagicMock(
        data=[{"id": "1", "content": "test", "metadata": {}, "similarity": 0.9}]
    )

    results = await search_chunks(
        embedding=[0.0] * 384,
        project_id="proj-1",
        top_k=5,
    )

    mock_supabase.rpc.assert_called_once_with("match_chunks", {
        "query_embedding": [0.0] * 384,
        "match_project_id": "proj-1",
        "match_count": 5,
        "filter_metadata": None,
    })
    assert len(results) == 1
    assert results[0]["content"] == "test"


@pytest.mark.asyncio
async def test_upsert_project_returns_id(mock_supabase):
    from vgv_rag.storage.queries import upsert_project

    mock_supabase.table.return_value.upsert.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-uuid-123"}]
    )

    project_id = await upsert_project(name="Test", notion_hub_url="https://notion.so/abc")
    assert project_id == "proj-uuid-123"
