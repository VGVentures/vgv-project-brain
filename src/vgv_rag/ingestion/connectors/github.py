import asyncio
import re
import time
from datetime import datetime, timezone

import httpx
import jwt
from github import Github

from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig

KEY_FILES = ["README.md", "CLAUDE.md", "AGENTS.md"]


class GitHubConnector:
    def __init__(
        self,
        app_id: str | None = None,
        private_key: str | None = None,
        installation_id: str | None = None,
        pat: str | None = None,
    ):
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._pat = pat
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _get_client(self) -> Github:
        """Get an authenticated GitHub client. Prefers App auth, falls back to PAT."""
        if self._app_id and self._private_key and self._installation_id:
            token = self._get_installation_token()
            return Github(token)
        elif self._pat:
            return Github(self._pat)
        else:
            raise RuntimeError("No GitHub credentials configured")

    def _get_installation_token(self) -> str:
        """Generate or reuse an installation access token."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": self._app_id,
        }
        encoded_jwt = jwt.encode(payload, self._private_key, algorithm="RS256")

        resp = httpx.post(
            f"https://api.github.com/app/installations/{self._installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        # Parse actual expiry from API response; fall back to 1 hour
        expires_at = data.get("expires_at")
        if expires_at:
            from datetime import datetime, timezone
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                self._token_expires_at = exp_dt.timestamp()
            except (ValueError, TypeError):
                self._token_expires_at = time.time() + 3600
        else:
            self._token_expires_at = time.time() + 3600
        return self._token

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "github", "source_url": url, "source_id": _extract_slug(url)}
            for url in config.github_repos
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        client = await asyncio.to_thread(self._get_client)
        repo = await asyncio.to_thread(lambda: client.get_repo(source.source_id))
        docs = []

        for filename in KEY_FILES:
            try:
                file_obj = await asyncio.to_thread(lambda f=filename: repo.get_contents(f))
                content = file_obj.decoded_content.decode("utf-8")
                docs.append(RawDocument(
                    source_url=f"https://github.com/{source.source_id}/blob/main/{filename}",
                    content=content,
                    title=filename,
                    date=datetime.now(timezone.utc),
                    artifact_type="document",
                    source_tool="github",
                ))
            except Exception:
                pass  # File doesn't exist in this repo

        pulls = await asyncio.to_thread(
            lambda: repo.get_pulls(state="all", sort="updated", direction="desc")
        )
        for pr in list(pulls)[:50]:
            if not pr.body or not pr.body.strip():
                continue
            pr_date = pr.updated_at
            if pr_date.tzinfo is None:
                pr_date = pr_date.replace(tzinfo=timezone.utc)
            if since and pr_date <= since:
                continue
            docs.append(RawDocument(
                source_url=pr.html_url,
                content=f"# {pr.title}\n\n{pr.body}",
                title=f"PR #{pr.number}: {pr.title}",
                author=pr.user.login if pr.user else None,
                date=pr_date,
                artifact_type="pr",
                source_tool="github",
            ))

        return docs


def _extract_slug(url: str) -> str:
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    return match.group(1) if match else url
