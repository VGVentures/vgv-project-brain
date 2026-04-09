from vgv_rag.ingestion.connectors.types import RawDocument


def build_chunk_metadata(doc: RawDocument, chunk_index: int, content: str) -> dict:
    return {
        "artifact_type": doc.artifact_type,
        "source_tool": doc.source_tool,
        "source_url": doc.source_url,
        "title": doc.title,
        "author": doc.author or "",
        "date": int(doc.date.timestamp()),
        "chunk_index": chunk_index,
        "content": content,
    }
