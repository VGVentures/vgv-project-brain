import asyncio
import re
from datetime import datetime, timezone
from github import Github
from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig

KEY_FILES = ["README.md", "CLAUDE.md", "AGENTS.md"]


class GitHubConnector:
    def __init__(self, token: str):
        self._client = Github(token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "github", "source_url": url, "source_id": _extract_slug(url)}
            for url in config.github_repos
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        repo = await asyncio.to_thread(lambda: self._client.get_repo(source.source_id))
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
