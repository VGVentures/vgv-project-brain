from __future__ import annotations
import asyncio
import logging
from functools import lru_cache

from pinecone import Pinecone

log = logging.getLogger(__name__)

_index = None


@lru_cache(maxsize=1)
def _get_index():
    from vgv_rag.config.settings import settings
    pc = Pinecone(api_key=settings.pinecone_api_key)
    return pc.Index(settings.pinecone_index_name)


def build_vector_id(source_id: str, chunk_index: int) -> str:
    return f"{source_id}:{chunk_index}"


def _translate_filters(filters: dict | None) -> dict | None:
    if not filters:
        return None
    return {k: {"$eq": v} for k, v in filters.items()}


async def upsert_vectors(namespace: str, vectors: list[dict]) -> None:
    index = _get_index()
    await asyncio.to_thread(
        lambda: index.upsert(vectors=vectors, namespace=namespace)
    )


async def query_vectors(
    namespace: str,
    embedding: list[float],
    top_k: int = 5,
    filters: dict | None = None,
) -> list[dict]:
    index = _get_index()
    pinecone_filter = _translate_filters(filters)

    result = await asyncio.to_thread(
        lambda: index.query(
            vector=embedding,
            namespace=namespace,
            top_k=top_k,
            include_metadata=True,
            filter=pinecone_filter,
        )
    )

    return [
        {
            "content": match.metadata.get("content", ""),
            "metadata": {k: v for k, v in match.metadata.items() if k != "content"},
            "score": match.score,
        }
        for match in result.matches
    ]


async def delete_by_source(namespace: str, source_id: str) -> None:
    index = _get_index()
    # List all vectors with the source_id prefix
    all_ids = []
    for page in await asyncio.to_thread(
        lambda: index.list(prefix=f"{source_id}:", namespace=namespace)
    ):
        all_ids.extend(page)

    if all_ids:
        await asyncio.to_thread(
            lambda: index.delete(ids=all_ids, namespace=namespace)
        )


async def verify_index() -> bool:
    """Check that the Pinecone index exists and is accessible."""
    try:
        index = _get_index()
        await asyncio.to_thread(lambda: index.describe_index_stats())
        return True
    except Exception as exc:
        log.error("Pinecone index verification failed: %s", exc)
        return False
