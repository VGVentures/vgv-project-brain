import asyncio
from pathlib import Path
from functools import lru_cache
from sentence_transformers import SentenceTransformer

CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache" / "sentence-transformers"
MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, cache_folder=str(CACHE_DIR))


async def embed(text: str) -> list[float]:
    """Embed a single text string. Runs model in a thread to avoid blocking."""
    model = _get_model()
    vector = await asyncio.to_thread(
        lambda: model.encode(text, normalize_embeddings=True).tolist()
    )
    return vector


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts efficiently in a single model call."""
    model = _get_model()
    vectors = await asyncio.to_thread(
        lambda: model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()
    )
    return vectors
