import asyncio
import re
from notion_client import Client
from vgv_rag.ingestion.connectors.types import ProjectConfig


def _extract_urls(block: dict) -> list[str]:
    urls = []
    block_type = block.get("type", "")
    rich_text = block.get(block_type, {}).get("rich_text", [])
    for rt in rich_text:
        if rt.get("href"):
            urls.append(rt["href"])
        if rt.get("text", {}).get("link", {}).get("url"):
            urls.append(rt["text"]["link"]["url"])
    if block_type == "bookmark":
        url = block.get("bookmark", {}).get("url")
        if url:
            urls.append(url)
    return urls


def _classify_url(url: str, config: ProjectConfig) -> None:
    if "slack.com/channels" in url or "slack.com/archives" in url:
        config.slack_channels.append(url)
    elif "github.com" in url:
        config.github_repos.append(url)
    elif "figma.com" in url:
        config.figma_files.append(url)
    elif "atlassian.net" in url or "jira" in url:
        config.jira_projects.append(url)
    elif "docs.google.com/spreadsheets" in url:
        pass  # Sheets deferred — intentionally ignored
    elif "drive.google.com/drive/folders" in url:
        config.google_drive_folders.append(url)
    elif "docs.google.com" in url or "drive.google.com/file" in url or "drive.google.com/open" in url:
        config.google_drive_docs.append(url)
    elif "drive.google.com" in url:
        config.google_drive_folders.append(url)  # Bare drive links are likely folders
    elif "notion.so" in url:
        config.notion_pages.append(url)


def _extract_page_id(url: str) -> str:
    clean = url.replace("-", "")
    match = re.search(r"([a-f0-9]{32})", clean)
    return match.group(1) if match else url


async def parse_project_hub(hub_url: str, notion_token: str) -> ProjectConfig:
    client = Client(auth=notion_token)
    page_id = _extract_page_id(hub_url)
    config = ProjectConfig()

    blocks = await asyncio.to_thread(
        lambda: client.blocks.children.list(block_id=page_id)
    )

    in_helpful_links = False
    for block in blocks.get("results", []):
        block_type = block.get("type", "")
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text).lower()

        if block_type.startswith("heading") and "helpful links" in text:
            in_helpful_links = True
            continue

        if block_type.startswith("heading") and in_helpful_links:
            break

        if in_helpful_links:
            for url in _extract_urls(block):
                _classify_url(url, config)

    return config
