import pytest


@pytest.mark.asyncio
async def test_embed_returns_384_dim_vector():
    from vgv_rag.processing.embedder import embed
    vector = await embed("hello world")
    assert len(vector) == 384
    assert all(isinstance(v, float) for v in vector)


@pytest.mark.asyncio
async def test_embed_different_texts_different_vectors():
    from vgv_rag.processing.embedder import embed
    v1 = await embed("project planning meeting")
    v2 = await embed("database schema migration")
    assert v1 != v2


@pytest.mark.asyncio
async def test_embed_batch():
    from vgv_rag.processing.embedder import embed_batch
    vectors = await embed_batch(["text one", "text two", "text three"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)
