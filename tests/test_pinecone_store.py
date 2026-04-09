import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_pinecone(mocker):
    mock_index = MagicMock()
    mocker.patch("vgv_rag.storage.pinecone_store._get_index", return_value=mock_index)
    return mock_index


@pytest.mark.asyncio
async def test_upsert_vectors(mock_pinecone):
    from vgv_rag.storage.pinecone_store import upsert_vectors

    vectors = [
        {"id": "src-1:0", "values": [0.1] * 1024, "metadata": {"content": "hello", "artifact_type": "prd"}},
    ]
    await upsert_vectors("project-uuid", vectors)
    mock_pinecone.upsert.assert_called_once()
    call_args = mock_pinecone.upsert.call_args
    assert call_args.kwargs["namespace"] == "project-uuid"


@pytest.mark.asyncio
async def test_query_vectors(mock_pinecone):
    from vgv_rag.storage.pinecone_store import query_vectors

    mock_pinecone.query.return_value = MagicMock(matches=[
        MagicMock(id="src-1:0", score=0.92, metadata={"content": "hello", "artifact_type": "prd"}),
    ])

    results = await query_vectors("project-uuid", [0.1] * 1024, top_k=5)
    assert len(results) == 1
    assert results[0]["content"] == "hello"
    assert results[0]["score"] == 0.92
    # Verify metadata split: content extracted, other fields in metadata dict
    assert "content" not in results[0]["metadata"]
    assert results[0]["metadata"]["artifact_type"] == "prd"


@pytest.mark.asyncio
async def test_query_vectors_with_filters(mock_pinecone):
    from vgv_rag.storage.pinecone_store import query_vectors

    mock_pinecone.query.return_value = MagicMock(matches=[
        MagicMock(id="src-1:0", score=0.85, metadata={"content": "design doc", "artifact_type": "prd"}),
    ])

    results = await query_vectors(
        "project-uuid", [0.1] * 1024, top_k=5,
        filters={"artifact_type": "prd"},
    )
    assert len(results) == 1
    # Verify filter was translated to Pinecone format
    call_kwargs = mock_pinecone.query.call_args.kwargs
    assert call_kwargs["filter"] == {"artifact_type": {"$eq": "prd"}}


@pytest.mark.asyncio
async def test_delete_by_source(mock_pinecone):
    from vgv_rag.storage.pinecone_store import delete_by_source

    # Mock list to return vector IDs with matching prefix
    mock_pinecone.list.return_value = [["src-1:0", "src-1:1"]]

    await delete_by_source("project-uuid", "src-1")
    mock_pinecone.delete.assert_called_once()
    call_kwargs = mock_pinecone.delete.call_args.kwargs
    assert "src-1:0" in call_kwargs["ids"]
    assert "src-1:1" in call_kwargs["ids"]
    assert call_kwargs["namespace"] == "project-uuid"


@pytest.mark.asyncio
async def test_delete_by_source_no_vectors(mock_pinecone):
    from vgv_rag.storage.pinecone_store import delete_by_source

    mock_pinecone.list.return_value = [[]]

    await delete_by_source("project-uuid", "src-1")
    mock_pinecone.delete.assert_not_called()


def test_build_vector_id():
    from vgv_rag.storage.pinecone_store import build_vector_id

    assert build_vector_id("src-uuid-123", 0) == "src-uuid-123:0"
    assert build_vector_id("src-uuid-123", 5) == "src-uuid-123:5"


def test_translate_filters():
    from vgv_rag.storage.pinecone_store import _translate_filters

    assert _translate_filters(None) is None
    assert _translate_filters({}) is None
    assert _translate_filters({"artifact_type": "prd"}) == {"artifact_type": {"$eq": "prd"}}
    assert _translate_filters({"artifact_type": "prd", "source_tool": "notion"}) == {
        "artifact_type": {"$eq": "prd"},
        "source_tool": {"$eq": "notion"},
    }
