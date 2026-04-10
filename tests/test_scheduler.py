import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from vgv_rag.ingestion.connectors.types import Source, RawDocument


@pytest.fixture(autouse=True)
def mock_storage(mocker):
    mocker.patch("vgv_rag.ingestion.scheduler.update_source_sync_status", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.upsert_vectors", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.embed_batch", new_callable=AsyncMock, return_value=[[0.0] * 1024])


@pytest.mark.asyncio
async def test_sync_source_upserts_vectors_with_correct_structure(mocker):
    from vgv_rag.ingestion.scheduler import sync_source, upsert_vectors

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

    upsert_vectors.assert_called_once()
    call_kwargs = upsert_vectors.call_args.kwargs
    assert call_kwargs["namespace"] == "proj-1"
    vectors = call_kwargs["vectors"]
    assert len(vectors) >= 1
    vec = vectors[0]
    assert vec["id"].startswith("src-1:")
    assert len(vec["values"]) == 1024
    assert "content" in vec["metadata"]
    assert vec["metadata"]["artifact_type"] == "meeting_note"


@pytest.mark.asyncio
async def test_sync_source_uses_program_id_namespace_for_program_sources(mocker):
    from vgv_rag.ingestion.scheduler import sync_source, upsert_vectors

    mock_connector = MagicMock()
    mock_connector.fetch_documents = AsyncMock(return_value=[
        RawDocument(
            source_url="https://drive.google.com/drive/folders/abc",
            content="Program-level SOW document content",
            title="SOW",
            date=datetime.now(timezone.utc),
            artifact_type="document",
            source_tool="google_drive",
        )
    ])

    source = Source(
        id="src-prog-1", project_id=None, connector="google_drive",
        source_url="https://drive.google.com/drive/folders/abc", source_id="abc",
        program_id="prog-1",
    )

    await sync_source(source=source, connector=mock_connector)

    upsert_vectors.assert_called_once()
    call_kwargs = upsert_vectors.call_args.kwargs
    assert call_kwargs["namespace"] == "prog-1"


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
