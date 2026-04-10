import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from vgv_rag.ingestion.connectors.types import ProgramConfig, ProjectConfig
from vgv_rag.ingestion.discovery import _extract_source_id, _classify_url_to_connector


def _make_page(page_id: str, title: str) -> dict:
    return {
        "id": page_id,
        "object": "page",
        "properties": {
            "title": {"title": [{"plain_text": title}]},
            "Name": {"title": [{"plain_text": title}]},
        },
    }


@pytest.fixture(autouse=True)
def mock_deps(mocker):
    mocker.patch("vgv_rag.ingestion.discovery.upsert_program", new_callable=AsyncMock, return_value="prog-1")
    mocker.patch("vgv_rag.ingestion.discovery.upsert_project", new_callable=AsyncMock, return_value="proj-1")
    mocker.patch("vgv_rag.ingestion.discovery.upsert_source", new_callable=AsyncMock, return_value="src-1")
    mocker.patch("vgv_rag.ingestion.discovery.list_all_programs", new_callable=AsyncMock, return_value=[])
    mocker.patch("vgv_rag.ingestion.discovery.list_projects_for_program", new_callable=AsyncMock, return_value=[])
    mocker.patch("vgv_rag.ingestion.discovery.list_sources_for_project", new_callable=AsyncMock, return_value=[])
    mocker.patch("vgv_rag.ingestion.discovery.update_source_sync_status", new_callable=AsyncMock)


@pytest.mark.asyncio
async def test_discover_all_finds_programs(mocker):
    from vgv_rag.ingestion.discovery import discover_all

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={
        "results": [_make_page("page-1", "Scooter's Coffee")],
        "has_more": False,
    })
    mocker.patch("vgv_rag.ingestion.discovery.AsyncClient", return_value=mock_client)

    program_config = ProgramConfig(
        project_hub_urls=["https://notion.so/hub1"],
        quick_links=["https://drive.google.com/drive/folders/abc"],
        communication_channels=["https://verygood.slack.com/archives/C123"],
    )
    mocker.patch("vgv_rag.ingestion.discovery.parse_program_page", new_callable=AsyncMock, return_value=program_config)
    mocker.patch("vgv_rag.ingestion.discovery.parse_project_hub", new_callable=AsyncMock, return_value=ProjectConfig(
        slack_channels=["https://verygood.slack.com/archives/C456"],
    ))

    stats = await discover_all("fake-token")

    assert stats["programs_found"] == 1
    assert stats["projects_found"] == 1
    assert stats["sources_created"] > 0


@pytest.mark.asyncio
async def test_discover_all_paginates_notion_search(mocker):
    from vgv_rag.ingestion.discovery import discover_all

    mock_client = MagicMock()
    # Page 1 has_more, page 2 completes
    mock_client.search = AsyncMock(side_effect=[
        {"results": [_make_page("page-1", "Program A")], "has_more": True, "next_cursor": "cursor-2"},
        {"results": [_make_page("page-2", "Program B")], "has_more": False},
    ])
    mocker.patch("vgv_rag.ingestion.discovery.AsyncClient", return_value=mock_client)
    mocker.patch("vgv_rag.ingestion.discovery.parse_program_page", new_callable=AsyncMock, return_value=ProgramConfig(
        project_hub_urls=[],
    ))

    stats = await discover_all("fake-token")

    assert mock_client.search.call_count == 2
    assert stats["programs_found"] == 2


@pytest.mark.asyncio
async def test_discover_all_skips_non_program_pages(mocker):
    from vgv_rag.ingestion.discovery import discover_all

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={
        "results": [_make_page("page-1", "Random Page"), _make_page("page-2", "Program X")],
        "has_more": False,
    })
    mocker.patch("vgv_rag.ingestion.discovery.AsyncClient", return_value=mock_client)

    # First page is not a program, second is
    mocker.patch("vgv_rag.ingestion.discovery.parse_program_page", new_callable=AsyncMock, side_effect=[
        None,  # Not a program page
        ProgramConfig(project_hub_urls=[]),
    ])

    stats = await discover_all("fake-token")
    assert stats["programs_found"] == 1


@pytest.mark.asyncio
async def test_discover_all_creates_program_level_sources(mocker):
    from vgv_rag.ingestion.discovery import discover_all, upsert_source

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={
        "results": [_make_page("page-1", "Program X")],
        "has_more": False,
    })
    mocker.patch("vgv_rag.ingestion.discovery.AsyncClient", return_value=mock_client)

    mocker.patch("vgv_rag.ingestion.discovery.parse_program_page", new_callable=AsyncMock, return_value=ProgramConfig(
        project_hub_urls=[],
        quick_links=["https://drive.google.com/drive/folders/abc"],
        communication_channels=["https://verygood.slack.com/archives/C123"],
    ))

    await discover_all("fake-token")

    # Should have created sources for the quick link and comm channel
    calls = upsert_source.call_args_list
    assert len(calls) >= 2
    # All should be program-level (program_id set, project_id absent)
    for call in calls:
        assert call.kwargs.get("program_id") == "prog-1"
        assert "project_id" not in call.kwargs, f"program-level source should not have project_id, got: {call.kwargs}"


@pytest.mark.asyncio
async def test_discover_all_marks_stale_sources(mocker):
    from vgv_rag.ingestion.discovery import discover_all, update_source_sync_status

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value={
        "results": [_make_page("page-1", "Program X")],
        "has_more": False,
    })
    mocker.patch("vgv_rag.ingestion.discovery.AsyncClient", return_value=mock_client)

    # Program with one project hub
    mocker.patch("vgv_rag.ingestion.discovery.parse_program_page", new_callable=AsyncMock, return_value=ProgramConfig(
        project_hub_urls=["https://notion.so/hub-a"],
    ))
    mocker.patch("vgv_rag.ingestion.discovery.parse_project_hub", new_callable=AsyncMock, return_value=ProjectConfig())

    # DB has a project under this program that was NOT discovered (stale)
    mocker.patch("vgv_rag.ingestion.discovery.list_projects_for_program", new_callable=AsyncMock, return_value=[
        {"id": "proj-stale", "notion_hub_url": "https://notion.so/hub-old"},
    ])
    mocker.patch("vgv_rag.ingestion.discovery.list_sources_for_project", new_callable=AsyncMock, return_value=[
        {"id": "src-stale"},
    ])

    await discover_all("fake-token")

    # The stale source should be marked as archived
    update_source_sync_status.assert_any_call("src-stale", "archived")


# --- Pure function tests ---

@pytest.mark.parametrize("url,expected", [
    ("https://verygood.slack.com/archives/C001ABCDEF", "C001ABCDEF"),
    ("https://github.com/VGVentures/my-app", "VGVentures/my-app"),
    ("https://figma.com/file/ABC123/Design", "ABC123"),
    ("https://figma.com/design/XYZ789/File", "XYZ789"),
    ("https://drive.google.com/drive/folders/1aBcDeFg", "1aBcDeFg"),
    ("https://docs.google.com/document/d/1xYzAbC/edit", "1xYzAbC"),
    ("https://notion.so/verygoodventures/My-Project-abc123def456abc123def456abc123de", "abc123def456abc123def456abc123de"),
])
def test_extract_source_id(url, expected):
    assert _extract_source_id(url) == expected


@pytest.mark.parametrize("url,expected", [
    ("https://verygood.slack.com/archives/C123", "slack"),
    ("https://github.com/VGVentures/repo", "github"),
    ("https://figma.com/file/ABC/Design", "figma"),
    ("https://verygoodventures.atlassian.net/jira/board", "atlassian"),
    ("https://drive.google.com/drive/folders/abc", "google_drive"),
    ("https://docs.google.com/document/d/abc/edit", "google_drive"),
    ("https://notion.so/page", "notion"),
    ("https://example.com/unknown", None),
])
def test_classify_url_to_connector(url, expected):
    assert _classify_url_to_connector(url) == expected
