import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_voyage(mocker):
    mock_client = MagicMock()
    mocker.patch("vgv_rag.processing.embedder.voyageai.Client", return_value=mock_client)
    # Clear lru_cache to prevent client leaking between tests
    from vgv_rag.processing.embedder import _get_client
    _get_client.cache_clear()
    return mock_client


@pytest.mark.asyncio
async def test_embed_calls_voyage_with_query_type(mock_voyage):
    from vgv_rag.processing.embedder import embed

    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])

    vector = await embed("search query")
    assert len(vector) == 1024
    mock_voyage.embed.assert_called_once()
    call_kwargs = mock_voyage.embed.call_args
    assert call_kwargs.kwargs["input_type"] == "query"


@pytest.mark.asyncio
async def test_embed_batch_calls_voyage_with_document_type(mock_voyage):
    from vgv_rag.processing.embedder import embed_batch

    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.1] * 1024, [0.2] * 1024])

    vectors = await embed_batch(["text one", "text two"])
    assert len(vectors) == 2
    assert all(len(v) == 1024 for v in vectors)
    call_kwargs = mock_voyage.embed.call_args
    assert call_kwargs.kwargs["input_type"] == "document"


@pytest.mark.asyncio
async def test_embed_batch_empty_returns_empty(mock_voyage):
    from vgv_rag.processing.embedder import embed_batch

    vectors = await embed_batch([])
    assert vectors == []
    mock_voyage.embed.assert_not_called()
