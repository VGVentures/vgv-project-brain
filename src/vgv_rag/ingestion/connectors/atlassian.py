import re
import base64
from datetime import datetime, timezone
import httpx
from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig


def _adf_to_text(node: dict | None) -> str:
    """Convert Atlassian Document Format to plain text."""
    if not node:
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_adf_to_text(child) for child in node.get("content", []))


class AtlassianConnector:
    def __init__(self, token: str, email: str, domain: str):
        self._token = token
        self._email = email
        self._domain = domain

    def _auth_header(self) -> str:
        creds = base64.b64encode(f"{self._email}:{self._token}".encode()).decode()
        return f"Basic {creds}"

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "atlassian", "source_url": url, "source_id": _extract_project_key(url)}
            for url in config.jira_projects
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        jql = f'project = "{source.source_id}" ORDER BY updated DESC'
        if since:
            date_str = since.strftime("%Y-%m-%d")
            jql = f'project = "{source.source_id}" AND updated > "{date_str}" ORDER BY updated DESC'

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{self._domain}/rest/api/3/search",
                params={
                    "jql": jql,
                    "maxResults": 100,
                    "fields": "summary,description,status,assignee,updated,comment",
                },
                headers={
                    "Authorization": self._auth_header(),
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        docs = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            desc = _adf_to_text(fields.get("description"))
            comments = "\n".join(
                f"[{c['author']['displayName']}]: {_adf_to_text(c['body'])}"
                for c in fields.get("comment", {}).get("comments", [])
            )

            content_parts = [
                f"Issue: {issue['key']} — {fields['summary']}",
                f"Status: {fields.get('status', {}).get('name', 'Unknown')}",
            ]
            if desc:
                content_parts += ["", "Description:", desc]
            if comments:
                content_parts += ["", "Comments:", comments]

            updated_str = fields["updated"].replace("+0000", "+00:00")
            updated = datetime.fromisoformat(updated_str)

            docs.append(RawDocument(
                source_url=f"https://{self._domain}/browse/{issue['key']}",
                content="\n".join(content_parts),
                title=f"{issue['key']}: {fields['summary']}",
                author=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                date=updated,
                artifact_type="issue",
                source_tool="atlassian",
            ))

        return docs


def _extract_project_key(url: str) -> str:
    match = re.search(r"projects/([A-Z][A-Z0-9]+)", url)
    return match.group(1) if match else url
