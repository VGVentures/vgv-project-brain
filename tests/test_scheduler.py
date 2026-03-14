import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from vgv_rag.ingestion.connectors.types import Source, RawDocument


@pytest.fixture(autouse=True)
def mock_storage(mocker):
    mocker.patch("vgv_rag.ingestion.scheduler.update_source_sync_status", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.delete_chunks_by_source", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.insert_chunks", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.embed_batch", new_callable=AsyncMock, return_value=[[0.0] * 384])


@pytest.mark.asyncio
async def test_sync_source_deletes_old_and_inserts_new(mocker):
    from vgv_rag.ingestion.scheduler import sync_source
    from vgv_rag.ingestion.scheduler import delete_chunks_by_source, insert_chunks

    mock_connector = MagicMock()
    mock_connector.fetch_documents = AsyncMock(return_value=[
        RawDocument(
            source_url="https://notion.so/abc",
            content="Meeting content about auth decisions",
            title="Meeting Notes",
            date=datetime.now(timezone.utc),
            artifact_type="meeting_note",
            source_tool="notion",
        )
    ])

    source = Source(
        id="src-1", project_id="proj-1", connector="notion",
        source_url="https://notion.so/abc", source_id="abc"
    )

    await sync_source(source=source, connector=mock_connector)

    delete_chunks_by_source.assert_called_once_with("src-1")
    insert_chunks.assert_called_once()


@pytest.mark.asyncio
async def test_sync_source_marks_error_on_exception(mocker):
    from vgv_rag.ingestion.scheduler import sync_source, update_source_sync_status

    mock_connector = MagicMock()
    mock_connector.fetch_documents = AsyncMock(side_effect=RuntimeError("API down"))

    source = Source(
        id="src-1", project_id="proj-1", connector="notion",
        source_url="https://notion.so/abc", source_id="abc"
    )

    await sync_source(source=source, connector=mock_connector)

    update_source_sync_status.assert_called_with("src-1", "error", "API down")
