# tests/test_tools.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_list_sources_project_not_found():
    from vgv_rag.server.tools.list_sources import handle_list_sources
    with patch("vgv_rag.server.tools.list_sources.get_project_by_name", return_value=None):
        result = await handle_list_sources(project="NonExistent", user_email="user@example.com")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_list_sources_no_sources():
    from vgv_rag.server.tools.list_sources import handle_list_sources
    with patch("vgv_rag.server.tools.list_sources.get_project_by_name", return_value={"id": "proj-1"}), \
         patch("vgv_rag.server.tools.list_sources.list_sources_for_project", return_value=[]):
        result = await handle_list_sources(project="MyProject", user_email="user@example.com")
    assert "no sources" in result.lower()


@pytest.mark.asyncio
async def test_list_sources_with_sources():
    from vgv_rag.server.tools.list_sources import handle_list_sources
    sources = [
        {"connector": "notion", "source_url": "https://notion.so/page", "sync_status": "success", "last_synced_at": "2026-03-14T10:00:00Z", "sync_error": None},
        {"connector": "slack", "source_url": "https://slack.com/channel", "sync_status": "error", "last_synced_at": None, "sync_error": "Rate limited"},
    ]
    with patch("vgv_rag.server.tools.list_sources.get_project_by_name", return_value={"id": "proj-1"}), \
         patch("vgv_rag.server.tools.list_sources.list_sources_for_project", return_value=sources):
        result = await handle_list_sources(project="MyProject", user_email="user@example.com")
    assert "notion" in result
    assert "slack" in result
    assert "Rate limited" in result


@pytest.mark.asyncio
async def test_ingest_document_no_content_or_url():
    from vgv_rag.server.tools.ingest import handle_ingest_document
    result = await handle_ingest_document(project="MyProject", content="", url="")
    assert "required" in result.lower()


@pytest.mark.asyncio
async def test_ingest_document_project_not_found():
    from vgv_rag.server.tools.ingest import handle_ingest_document
    with patch("vgv_rag.server.tools.ingest.get_project_by_name", return_value=None):
        result = await handle_ingest_document(project="NonExistent", content="some text")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_ingest_document_with_content():
    from vgv_rag.server.tools.ingest import handle_ingest_document
    with patch("vgv_rag.server.tools.ingest.get_project_by_name", return_value={"id": "proj-1"}), \
         patch("vgv_rag.server.tools.ingest.upsert_source", return_value="src-1"), \
         patch("vgv_rag.server.tools.ingest.embed_batch", return_value=[[0.1] * 384]), \
         patch("vgv_rag.server.tools.ingest.insert_chunks", return_value=None):
        result = await handle_ingest_document(project="MyProject", content="This is a test document about the project architecture.", artifact_type="document")
    assert "chunk" in result.lower()
    assert "MyProject" in result
