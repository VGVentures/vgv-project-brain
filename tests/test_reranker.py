import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_voyage(mocker):
    mock_client = MagicMock()
    mocker.patch("vgv_rag.processing.reranker.voyageai.Client", return_value=mock_client)
    # Clear lru_cache to prevent client leaking between tests
    from vgv_rag.processing.reranker import _get_client
    _get_client.cache_clear()
    return mock_client


@pytest.mark.asyncio
async def test_rerank_returns_sorted_results(mock_voyage):
    from vgv_rag.processing.reranker import rerank

    mock_voyage.rerank.return_value = MagicMock(results=[
        MagicMock(index=1, relevance_score=0.95),
        MagicMock(index=0, relevance_score=0.72),
    ])

    documents = [
        {"content": "low relevance", "metadata": {}},
        {"content": "high relevance", "metadata": {}},
    ]
    results = await rerank("test query", documents, top_k=2)
    assert len(results) == 2
    assert results[0]["content"] == "high relevance"
    assert results[0]["relevance_score"] == 0.95


@pytest.mark.asyncio
async def test_rerank_falls_back_on_failure(mock_voyage):
    from vgv_rag.processing.reranker import rerank

    mock_voyage.rerank.side_effect = Exception("API error")

    documents = [
        {"content": "doc A", "metadata": {}},
        {"content": "doc B", "metadata": {}},
    ]
    results = await rerank("test query", documents, top_k=2)
    # Should return original documents unchanged on failure
    assert len(results) == 2
    assert results[0]["content"] == "doc A"


@pytest.mark.asyncio
async def test_rerank_respects_top_k(mock_voyage):
    from vgv_rag.processing.reranker import rerank

    mock_voyage.rerank.return_value = MagicMock(results=[
        MagicMock(index=0, relevance_score=0.9),
    ])

    documents = [
        {"content": "doc A", "metadata": {}},
        {"content": "doc B", "metadata": {}},
        {"content": "doc C", "metadata": {}},
    ]
    results = await rerank("test query", documents, top_k=1)
    assert len(results) == 1
