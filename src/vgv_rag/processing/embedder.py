import asyncio
from functools import lru_cache

import voyageai

MODEL = "voyage-4-lite"


@lru_cache(maxsize=1)
def _get_client() -> voyageai.Client:
    return voyageai.Client()  # reads VOYAGE_API_KEY from env


async def embed(text: str) -> list[float]:
    """Embed a single text for query-time search."""
    client = _get_client()
    result = await asyncio.to_thread(
        lambda: client.embed(
            texts=[text], model=MODEL, input_type="query",
        )
    )
    return result.embeddings[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts for document ingestion."""
    if not texts:
        return []
    client = _get_client()
    result = await asyncio.to_thread(
        lambda: client.embed(
            texts=texts, model=MODEL, input_type="document",
        )
    )
    return result.embeddings
