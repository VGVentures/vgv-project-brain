import pytest

MOCK_PROGRAM_BLOCKS = {
    "results": [
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Project Hubs"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "SCO_001 Hub", "href": "https://notion.so/verygoodventures/SCO-001-Hub-abc123def456abc123def456abc123de"},
                ],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "SCO_002 Hub", "href": "https://notion.so/verygoodventures/SCO-002-Hub-def456abc123def456abc123def456ab"},
                ],
            },
        },
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Quick Links"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "SOW", "href": "https://drive.google.com/drive/folders/1aBcDeFg"},
                ],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "Account Plan", "href": "https://docs.google.com/document/d/1xYz/edit"},
                ],
            },
        },
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Communication Channels"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "Slack", "href": "https://verygood.slack.com/archives/C001ABCDEF"},
                ],
            },
        },
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Other Section"}]},
        },
    ],
}

MOCK_NON_PROGRAM_BLOCKS = {
    "results": [
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Helpful Links"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "GitHub", "href": "https://github.com/org/repo"},
                ],
            },
        },
    ],
}


@pytest.fixture
def mock_notion_program(mocker):
    mock = mocker.MagicMock()
    mock.blocks.children.list.return_value = MOCK_PROGRAM_BLOCKS
    mocker.patch("vgv_rag.ingestion.program_parser.Client", return_value=mock)
    return mock


@pytest.fixture
def mock_notion_non_program(mocker):
    mock = mocker.MagicMock()
    mock.blocks.children.list.return_value = MOCK_NON_PROGRAM_BLOCKS
    mocker.patch("vgv_rag.ingestion.program_parser.Client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_extracts_project_hub_urls(mock_notion_program):
    from vgv_rag.ingestion.program_parser import parse_program_page

    config = await parse_program_page(
        "https://notion.so/verygoodventures/Scooters-abc123def456abc123def456abc123de",
        "fake-token",
    )
    assert config is not None
    assert len(config.project_hub_urls) == 2
    assert any("SCO-001" in url for url in config.project_hub_urls)
    assert any("SCO-002" in url for url in config.project_hub_urls)


@pytest.mark.asyncio
async def test_extracts_quick_links(mock_notion_program):
    from vgv_rag.ingestion.program_parser import parse_program_page

    config = await parse_program_page(
        "https://notion.so/verygoodventures/Scooters-abc123def456abc123def456abc123de",
        "fake-token",
    )
    assert config is not None
    assert len(config.quick_links) == 2
    assert any("drive.google.com" in url for url in config.quick_links)
    assert any("docs.google.com" in url for url in config.quick_links)


@pytest.mark.asyncio
async def test_extracts_communication_channels(mock_notion_program):
    from vgv_rag.ingestion.program_parser import parse_program_page

    config = await parse_program_page(
        "https://notion.so/verygoodventures/Scooters-abc123def456abc123def456abc123de",
        "fake-token",
    )
    assert config is not None
    assert len(config.communication_channels) == 1
    assert "slack.com" in config.communication_channels[0]


@pytest.mark.asyncio
async def test_returns_none_for_non_program_page(mock_notion_non_program):
    from vgv_rag.ingestion.program_parser import parse_program_page

    config = await parse_program_page(
        "https://notion.so/verygoodventures/SomePage-abc123def456abc123def456abc123de",
        "fake-token",
    )
    assert config is None


@pytest.mark.asyncio
async def test_stops_at_next_heading_after_section(mock_notion_program):
    """Each section should stop collecting at the next heading."""
    from vgv_rag.ingestion.program_parser import parse_program_page

    config = await parse_program_page(
        "https://notion.so/verygoodventures/Scooters-abc123def456abc123def456abc123de",
        "fake-token",
    )
    assert config is not None
    # Communication channels should only have the Slack link, not bleed into "Other Section"
    assert len(config.communication_channels) == 1
