import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from vgv_rag.storage.queries import (
    update_source_sync_status,
    delete_chunks_by_source,
    insert_chunks,
    list_sources_for_project,
)
from vgv_rag.processing.chunker import chunk
from vgv_rag.processing.embedder import embed_batch
from vgv_rag.processing.metadata import build_chunk_metadata
from vgv_rag.ingestion.connectors.types import Source, Connector

log = logging.getLogger(__name__)


async def sync_source(source: Source, connector) -> None:
    await update_source_sync_status(source.id, "syncing")
    try:
        docs = await connector.fetch_documents(source, source.last_synced_at)
        await delete_chunks_by_source(source.id)

        for doc in docs:
            chunks = chunk(doc.content, doc.artifact_type)
            if not chunks:
                continue
            embeddings = await embed_batch(chunks)
            rows = [
                {
                    "project_id": source.project_id,
                    "source_id": source.id,
                    "content": text,
                    "embedding": embeddings[i],
                    "metadata": build_chunk_metadata(doc, i),
                }
                for i, text in enumerate(chunks)
            ]
            await insert_chunks(rows)

        await update_source_sync_status(source.id, "success")
        log.info("Synced source %s (%s)", source.id, source.connector)

    except Exception as exc:
        msg = str(exc)
        log.error("Sync failed for source %s: %s", source.id, msg)
        await update_source_sync_status(source.id, "error", msg)


def is_business_hours() -> bool:
    from datetime import datetime
    now = datetime.now()
    return 1 <= now.isoweekday() <= 5 and 8 <= now.hour <= 20


def start_scheduler(get_connector) -> AsyncIOScheduler:
    from vgv_rag.storage.client import get_client

    async def run_sync():
        log.info("Sync cycle starting...")
        client = get_client()
        projects = client.table("projects").select("id").execute()
        for project in (projects.data or []):
            sources = await list_sources_for_project(project["id"])
            for source_dict in sources:
                connector = get_connector(source_dict["connector"])
                if not connector:
                    continue
                source = Source(
                    id=source_dict["id"],
                    project_id=source_dict["project_id"],
                    connector=source_dict["connector"],
                    source_url=source_dict["source_url"],
                    source_id=source_dict["source_id"],
                    last_synced_at=source_dict.get("last_synced_at"),
                )
                await sync_source(source=source, connector=connector)
        log.info("Sync cycle complete.")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: run_sync() if is_business_hours() else None,
        "cron", minute="*/15", hour="8-20", day_of_week="mon-fri",
    )
    scheduler.add_job(
        lambda: run_sync() if not is_business_hours() else None,
        "cron", minute=0,
    )
    scheduler.start()
    log.info("Sync scheduler started.")
    return scheduler
