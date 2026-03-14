import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


@pytest.fixture
def mock_github(mocker):
    mock_repo = MagicMock()

    mock_file = MagicMock()
    mock_file.decoded_content = b"# README\nThis project uses Supabase for auth."
    mock_repo.get_contents.return_value = mock_file

    mock_pr = MagicMock()
    mock_pr.number = 1
    mock_pr.title = "Add auth middleware"
    mock_pr.body = "Implements JWT validation using Supabase."
    mock_pr.user.login = "alice"
    mock_pr.updated_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    mock_pr.html_url = "https://github.com/vgv/repo/pull/1"
    mock_repo.get_pulls.return_value = [mock_pr]

    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)
    return mock_github_client


@pytest.mark.asyncio
async def test_github_fetches_readme_and_prs(mock_github):
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = GitHubConnector("fake-pat")
    source = Source(
        id="s1", project_id="p1", connector="github",
        source_url="https://github.com/vgv/repo", source_id="vgv/repo"
    )

    docs = await connector.fetch_documents(source)

    readme_docs = [d for d in docs if "README" in d.title]
    pr_docs = [d for d in docs if d.artifact_type == "pr"]

    assert len(readme_docs) > 0
    assert "Supabase" in readme_docs[0].content
    assert len(pr_docs) > 0
    assert "JWT validation" in pr_docs[0].content
