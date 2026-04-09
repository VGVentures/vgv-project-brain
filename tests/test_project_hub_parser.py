import pytest

MOCK_BLOCKS = {
    "results": [
        {
            "type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": "Helpful Links"}]},
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "Slack channel", "href": "https://verygood.slack.com/archives/C001ABCDEF"}
                ],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "GitHub", "href": "https://github.com/verygoodventures/proj-alpha"}
                ],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "Figma", "href": "https://figma.com/file/ABC123/Design-System"}
                ],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"plain_text": "Jira", "href": "https://verygoodventures.atlassian.net/jira/software/projects/PROJ"}
                ],
            },
        },
    ],
    "has_more": False,
}


@pytest.fixture
def mock_notion(mocker):
    mock = mocker.MagicMock()
    mock.blocks.children.list.return_value = MOCK_BLOCKS
    mocker.patch("vgv_rag.ingestion.project_hub_parser.Client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_parses_slack_channel(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("C001ABCDEF" in url or "slack.com" in url for url in config.slack_channels)


@pytest.mark.asyncio
async def test_parses_github_repo(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("github.com" in url for url in config.github_repos)


@pytest.mark.asyncio
async def test_parses_figma_file(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("figma.com" in url for url in config.figma_files)


@pytest.mark.asyncio
async def test_parses_jira_project(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("atlassian.net" in url for url in config.jira_projects)


# --- Google Drive URL classification tests ---

@pytest.mark.parametrize("url,field", [
    # Shared folder
    ("https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsT", "google_drive_folders"),
    # Google Doc
    ("https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsT/edit", "google_drive_docs"),
    # Google Slides
    ("https://docs.google.com/presentation/d/1aBcDeFgHiJkLmNoPqRsT/edit", "google_drive_docs"),
    # Direct file link
    ("https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsT/view", "google_drive_docs"),
    # open?id= format
    ("https://drive.google.com/open?id=1aBcDeFgHiJkLmNoPqRsT", "google_drive_docs"),
])
def test_classify_google_urls(url, field):
    from vgv_rag.ingestion.connectors.types import ProjectConfig
    from vgv_rag.ingestion.project_hub_parser import _classify_url

    config = ProjectConfig()
    _classify_url(url, config)
    assert url in getattr(config, field)


def test_classify_google_sheets_ignored():
    """Sheets are deferred — URLs should not be classified."""
    from vgv_rag.ingestion.connectors.types import ProjectConfig
    from vgv_rag.ingestion.project_hub_parser import _classify_url

    config = ProjectConfig()
    _classify_url("https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsT/edit", config)
    assert not config.google_drive_folders
    assert not config.google_drive_docs
