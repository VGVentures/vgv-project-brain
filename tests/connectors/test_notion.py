import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


@pytest.fixture
def mock_notion_client(mocker):
    mock = MagicMock()
    mock.search.return_value = {
        "results": [
            {
                "id": "page-1",
                "url": "https://notion.so/page-1",
                "object": "page",
                "last_edited_time": "2026-02-01T00:00:00.000Z",
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "Meeting Notes Feb 2026"}]
                    }
                },
            }
        ]
    }
    mock.blocks.children.list.return_value = {
        "results": [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"plain_text": "We decided to use Supabase."}]
                }
            },
        ],
        "has_more": False,
    }
    mocker.patch("vgv_rag.ingestion.connectors.notion.Client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_notion_fetch_returns_documents(mock_notion_client):
    from vgv_rag.ingestion.connectors.notion import NotionConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = NotionConnector("fake-token")
    source = Source(
        id="src-1", project_id="proj-1", connector="notion",
        source_url="https://notion.so/page-1", source_id="page-1"
    )

    docs = await connector.fetch_documents(source)

    assert len(docs) == 1
    assert "Supabase" in docs[0].content
    assert docs[0].source_tool == "notion"
    assert docs[0].artifact_type == "meeting_note"


@pytest.mark.asyncio
async def test_notion_incremental_skips_old_pages(mock_notion_client):
    from vgv_rag.ingestion.connectors.notion import NotionConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = NotionConnector("fake-token")
    source = Source(
        id="src-1", project_id="proj-1", connector="notion",
        source_url="https://notion.so/page-1", source_id="page-1"
    )

    # Since date is AFTER the page's last_edited_time
    since = datetime(2026, 3, 1, tzinfo=timezone.utc)
    docs = await connector.fetch_documents(source, since=since)
    assert docs == []
