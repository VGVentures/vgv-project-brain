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
