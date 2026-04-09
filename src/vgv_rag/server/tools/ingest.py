# src/vgv_rag/server/tools/ingest.py
import httpx
from vgv_rag.processing.embedder import embed_batch
from vgv_rag.processing.chunker import chunk
from vgv_rag.processing.metadata import build_chunk_metadata
from vgv_rag.storage.supabase_queries import upsert_source, get_project_by_name
from vgv_rag.storage.pinecone_store import upsert_vectors, build_vector_id
from vgv_rag.ingestion.connectors.types import RawDocument
from datetime import datetime, timezone


async def handle_ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    if not content and not url:
        return "Error: either content or url is required."

    proj = await get_project_by_name(project)
    if not proj:
        return f"Project not found: {project}"

    text = content
    if url and not content:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text
        except httpx.HTTPError as exc:
            return f"Error fetching URL: {exc}"

    source_id = await upsert_source(
        project_id=proj["id"],
        connector="manual",
        source_url=url or "inline",
        source_id=url or f"manual-{int(datetime.now(timezone.utc).timestamp())}",
    )

    chunks = chunk(text, artifact_type)
    embeddings = await embed_batch(chunks)

    doc = RawDocument(
        source_url=url or "inline",
        content=text,
        title=url or "Manual document",
        date=datetime.now(timezone.utc),
        artifact_type=artifact_type,
        source_tool="manual",
    )

    vectors = [
        {
            "id": build_vector_id(source_id, i),
            "values": embeddings[i],
            "metadata": build_chunk_metadata(doc, i, c),
        }
        for i, c in enumerate(chunks)
    ]
    await upsert_vectors(namespace=proj["id"], vectors=vectors)

    return f"Indexed {len(chunks)} chunk(s) from {'URL' if url else 'inline content'} into project \"{project}\"."
