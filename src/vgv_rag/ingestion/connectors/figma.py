import re
from datetime import datetime, timezone
import httpx
from vgv_rag.ingestion.connectors.types import RawDocument, Source, ProjectConfig

FIGMA_API = "https://api.figma.com/v1"


class FigmaConnector:
    def __init__(self, token: str):
        self._token = token

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "figma", "source_url": url, "source_id": _extract_file_key(url)}
            for url in config.figma_files
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        # Figma has no reliable incremental API — always full resync
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FIGMA_API}/files/{source.source_id}",
                headers={"X-Figma-Token": self._token},
            )
            response.raise_for_status()
            file_data = response.json()

        docs: list[RawDocument] = []
        _extract_components(
            node=file_data["document"],
            file_key=source.source_id,
            file_name=file_data.get("name", "Figma File"),
            docs=docs,
        )
        return docs


def _extract_components(node: dict, file_key: str, file_name: str, docs: list[RawDocument]) -> None:
    if node.get("type") in ("COMPONENT", "COMPONENT_SET"):
        parts = [f"Component: {node['name']}"]
        if node.get("description"):
            parts.append(f"Description: {node['description']}")
        if node.get("type") == "COMPONENT_SET" and node.get("children"):
            variants = ", ".join(c["name"] for c in node["children"])
            parts.append(f"Variants: {variants}")

        docs.append(RawDocument(
            source_url=f"https://figma.com/file/{file_key}?node-id={node.get('id', '')}",
            content="\n".join(parts),
            title=f"{file_name} — {node['name']}",
            date=datetime.now(timezone.utc),
            artifact_type="design_spec",
            source_tool="figma",
        ))

    for child in node.get("children", []):
        _extract_components(child, file_key, file_name, docs)


def _extract_file_key(url: str) -> str:
    match = re.search(r"figma\.com/(?:file|design)/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else url
