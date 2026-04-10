import pytest
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


@pytest.fixture(scope="module")
def rsa_private_key_pem():
    """Generate an RSA key once for all GitHub App auth tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def mock_repo():
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
    return mock_repo


@pytest.fixture
def mock_github(mocker, mock_repo):
    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)
    return mock_github_client


@pytest.mark.asyncio
async def test_github_fetches_readme_and_prs_with_pat(mock_github):
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = GitHubConnector(pat="fake-pat")
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


@pytest.mark.asyncio
async def test_github_app_auth_generates_jwt_and_exchanges_token(mocker, mock_repo, rsa_private_key_pem):
    from vgv_rag.ingestion.connectors.github import GitHubConnector

    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    github_class = mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)

    mock_response = MagicMock()
    mock_response.json.return_value = {"token": "ghs_fake_installation_token"}
    mock_response.raise_for_status = MagicMock()
    mocker.patch("vgv_rag.ingestion.connectors.github.httpx.post", return_value=mock_response)

    connector = GitHubConnector(
        app_id="12345",
        private_key=rsa_private_key_pem,
        installation_id="67890",
    )

    from vgv_rag.ingestion.connectors.types import Source
    source = Source(
        id="s1", project_id="p1", connector="github",
        source_url="https://github.com/vgv/repo", source_id="vgv/repo"
    )

    docs = await connector.fetch_documents(source)

    # Should have used the installation token
    github_class.assert_called_with("ghs_fake_installation_token")
    assert len(docs) > 0


@pytest.mark.asyncio
async def test_github_app_reuses_cached_token(mocker, mock_repo, rsa_private_key_pem):
    from vgv_rag.ingestion.connectors.github import GitHubConnector

    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)

    mock_response = MagicMock()
    mock_response.json.return_value = {"token": "ghs_cached_token"}
    mock_response.raise_for_status = MagicMock()
    mock_post = mocker.patch("vgv_rag.ingestion.connectors.github.httpx.post", return_value=mock_response)

    connector = GitHubConnector(app_id="12345", private_key=rsa_private_key_pem, installation_id="67890")

    from vgv_rag.ingestion.connectors.types import Source
    source = Source(
        id="s1", project_id="p1", connector="github",
        source_url="https://github.com/vgv/repo", source_id="vgv/repo"
    )

    # First call generates token
    await connector.fetch_documents(source)
    assert mock_post.call_count == 1

    # Second call reuses cached token
    await connector.fetch_documents(source)
    assert mock_post.call_count == 1  # No new HTTP call


@pytest.mark.asyncio
async def test_github_app_refreshes_expired_token(mocker, mock_repo, rsa_private_key_pem):
    from vgv_rag.ingestion.connectors.github import GitHubConnector

    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)

    mock_response = MagicMock()
    mock_response.json.return_value = {"token": "ghs_refreshed_token"}
    mock_response.raise_for_status = MagicMock()
    mock_post = mocker.patch("vgv_rag.ingestion.connectors.github.httpx.post", return_value=mock_response)

    connector = GitHubConnector(app_id="12345", private_key=rsa_private_key_pem, installation_id="67890")

    from vgv_rag.ingestion.connectors.types import Source
    source = Source(
        id="s1", project_id="p1", connector="github",
        source_url="https://github.com/vgv/repo", source_id="vgv/repo"
    )

    # First call
    await connector.fetch_documents(source)
    assert mock_post.call_count == 1

    # Simulate token expiry by setting expires_at to the past
    connector._token_expires_at = time.time() - 100

    # Second call should refresh
    await connector.fetch_documents(source)
    assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_github_fallback_to_pat_when_no_app_vars(mock_github):
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = GitHubConnector(pat="ghp_test")
    source = Source(
        id="s1", project_id="p1", connector="github",
        source_url="https://github.com/vgv/repo", source_id="vgv/repo"
    )

    docs = await connector.fetch_documents(source)
    assert len(docs) > 0


def test_github_raises_when_no_credentials():
    from vgv_rag.ingestion.connectors.github import GitHubConnector

    connector = GitHubConnector()
    with pytest.raises(RuntimeError, match="No GitHub credentials"):
        connector._get_client()


@pytest.mark.asyncio
async def test_github_discover_sources():
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.types import ProjectConfig

    connector = GitHubConnector(pat="fake")
    config = ProjectConfig(github_repos=["https://github.com/VGVentures/my-app"])

    sources = await connector.discover_sources(config)
    assert len(sources) == 1
    assert sources[0]["source_id"] == "VGVentures/my-app"
