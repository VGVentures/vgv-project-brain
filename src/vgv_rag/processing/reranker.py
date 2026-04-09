import asyncio
import logging
from functools import lru_cache

import voyageai

log = logging.getLogger(__name__)

MODEL = "rerank-2-lite"


@lru_cache(maxsize=1)
def _get_client() -> voyageai.Client:
    return voyageai.Client()


async def rerank(
    query: str, documents: list[dict], top_k: int = 5
) -> list[dict]:
    """Rerank documents using Voyage.ai. Falls back to original order on failure."""
    client = _get_client()
    texts = [doc["content"] for doc in documents]

    try:
        result = await asyncio.to_thread(
            lambda: client.rerank(
                query=query, documents=texts, model=MODEL, top_k=top_k,
            )
        )
        return [
            {**documents[r.index], "relevance_score": r.relevance_score}
            for r in result.results
        ]
    except Exception as exc:
        log.warning("Reranker failed, returning raw results: %s", exc)
        return documents[:top_k]
