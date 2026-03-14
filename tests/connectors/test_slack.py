import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


BOT_SUBTYPES = {"channel_join", "bot_message"}


@pytest.fixture
def mock_slack(mocker):
    mock = MagicMock()
    mock.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {
                "ts": "1706745600.000001",
                "text": "Decided to use Supabase for auth.",
                "user": "U001",
            },
            {
                "ts": "1706745601.000001",
                "text": "",
                "user": "U002",
                "subtype": "channel_join",
            },
            {
                "ts": "1706745602.000001",
                "text": "Another message",
                "user": "U003",
                "bot_id": "B001",
            },
        ],
        "has_more": False,
    }
    mock.conversations_replies.return_value = {"ok": True, "messages": [], "has_more": False}
    mock.conversations_info.return_value = {"ok": True, "channel": {"name": "proj-alpha"}}
    mock.users_info.return_value = {"ok": True, "user": {"real_name": "Alice"}}
    mocker.patch("vgv_rag.ingestion.connectors.slack.WebClient", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_slack_filters_joins_and_bots(mock_slack):
    from vgv_rag.ingestion.connectors.slack import SlackConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = SlackConnector("fake-token")
    source = Source(
        id="s1", project_id="p1", connector="slack",
        source_url="https://app.slack.com/client/T001/C001", source_id="C001"
    )

    docs = await connector.fetch_documents(source)
    # Only the first message should pass (second is channel_join, third is bot)
    assert len(docs) == 1
    assert "Supabase" in docs[0].content
    assert docs[0].artifact_type == "slack_thread"


@pytest.mark.asyncio
async def test_slack_discover_sources(mock_slack):
    from vgv_rag.ingestion.connectors.slack import SlackConnector
    from vgv_rag.ingestion.connectors.types import ProjectConfig

    connector = SlackConnector("fake-token")
    config = ProjectConfig(slack_channels=["https://slack.com/archives/C001ABCDEF"])

    sources = await connector.discover_sources(config)
    assert len(sources) == 1
    assert sources[0]["source_id"] == "C001ABCDEF"
