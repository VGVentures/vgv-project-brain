import asyncio
import re
from datetime import datetime, timezone
from notion_client import Client
from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig, detect_artifact_type


def _extract_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts)
    return "Untitled"


def _blocks_to_text(blocks: list[dict]) -> str:
    lines = []
    for block in blocks:
        block_type = block.get("type", "")
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _extract_id(url: str) -> str:
    match = re.search(r"([a-f0-9]{32})$", url)
    return match.group(1) if match else url


class NotionConnector:
    def __init__(self, token: str):
        self._client = Client(auth=token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "notion", "source_url": url, "source_id": _extract_id(url)}
            for url in config.notion_pages
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        search_result = await asyncio.to_thread(
            lambda: self._client.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
            )
        )

        docs = []
        for page in search_result.get("results", []):
            edited = datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00"))
            if since and edited <= since:
                continue

            title = _extract_title(page)
            blocks_result = await asyncio.to_thread(
                lambda pid=page["id"]: self._client.blocks.children.list(block_id=pid)
            )
            content = _blocks_to_text(blocks_result.get("results", []))
            if not content.strip():
                continue

            docs.append(RawDocument(
                source_url=page["url"],
                content=content,
                title=title,
                author=None,
                date=edited,
                artifact_type=detect_artifact_type(title),
                source_tool="notion",
            ))

        return docs
