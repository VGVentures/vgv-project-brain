import asyncio
import dataclasses
import logging
import re
from notion_client import AsyncClient

from vgv_rag.ingestion.program_parser import parse_program_page
from vgv_rag.ingestion.project_hub_parser import parse_project_hub
from vgv_rag.ingestion.connectors.types import ProgramConfig, ProjectConfig
from vgv_rag.storage.supabase_queries import (
    upsert_program, upsert_project, upsert_source,
    list_all_programs, list_projects_for_program, list_sources_for_project,
    update_source_sync_status,
)

log = logging.getLogger(__name__)

_notion_semaphore = asyncio.Semaphore(3)


async def discover_all(notion_token: str) -> dict:
    """Crawl Notion, discover programs and projects, upsert records.

    Returns summary: {"programs_found": N, "projects_found": N, "sources_created": N}
    """
    client = AsyncClient(auth=notion_token)
    stats = {"programs_found": 0, "projects_found": 0, "sources_created": 0}

    all_pages = await _search_all_pages(client)
    discovered_project_urls: set[str] = set()
    discovered_program_ids: set[str] = set()

    for page in all_pages:
        page_url = _page_to_url(page)
        program_config = await parse_program_page(page_url, notion_token)
        if program_config is None:
            continue

        program_name = _extract_title(page)
        program_id = await upsert_program(
            name=program_name,
            notion_page_url=page_url,
            config=dataclasses.asdict(program_config),
        )
        stats["programs_found"] += 1
        discovered_program_ids.add(program_id)

        stats["sources_created"] += await _create_program_sources(
            program_id, program_config
        )

        for hub_url in program_config.project_hub_urls:
            project_config = await parse_project_hub(hub_url, notion_token)
            if not project_config:
                continue

            project_name = _extract_project_name(hub_url)
            project_id = await upsert_project(
                name=project_name,
                notion_hub_url=hub_url,
                config=dataclasses.asdict(project_config),
                program_id=program_id,
            )
            stats["projects_found"] += 1
            discovered_project_urls.add(hub_url)

            stats["sources_created"] += await _create_project_sources(
                project_id, project_config
            )

    await _mark_stale_sources(discovered_program_ids, discovered_project_urls)

    log.info("Discovery complete: %s", stats)
    return stats


async def _search_all_pages(client: AsyncClient) -> list[dict]:
    pages = []
    cursor = None
    while True:
        async with _notion_semaphore:
            result = await client.search(
                filter={"property": "object", "value": "page"},
                start_cursor=cursor,
                page_size=100,
            )
        pages.extend(result["results"])
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]
    return pages


def _page_to_url(page: dict) -> str:
    page_id = page["id"].replace("-", "")
    return f"https://notion.so/{page_id}"


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("title"):
            parts = prop["title"]
            return "".join(p.get("plain_text", "") for p in parts)
    return "Untitled"


def _extract_project_name(hub_url: str) -> str:
    match = re.search(r"notion\.so/(?:[^/]+/)?([^-]+-[^-]+(?:-[^-]+)*)-[a-f0-9]{32}", hub_url)
    if match:
        return match.group(1).replace("-", " ")
    # Fallback: use the last path segment
    parts = hub_url.rstrip("/").split("/")
    return parts[-1].split("-")[0] if parts else "Unknown"


async def _create_program_sources(program_id: str, config: ProgramConfig) -> int:
    count = 0
    all_urls = config.quick_links + config.communication_channels
    for url in all_urls:
        connector = _classify_url_to_connector(url)
        if connector:
            await upsert_source(
                connector=connector,
                source_url=url,
                source_id=_extract_source_id(url),
                program_id=program_id,
            )
            count += 1
    return count


async def _create_project_sources(project_id: str, config: ProjectConfig) -> int:
    count = 0
    source_lists = [
        ("slack", config.slack_channels),
        ("github", config.github_repos),
        ("figma", config.figma_files),
        ("atlassian", config.jira_projects),
        ("notion", config.notion_pages),
        ("google_drive", config.google_drive_folders),
        ("google_drive", config.google_drive_docs),
    ]
    for connector, urls in source_lists:
        for url in urls:
            await upsert_source(
                connector=connector,
                source_url=url,
                source_id=_extract_source_id(url),
                project_id=project_id,
            )
            count += 1
    return count


def _classify_url_to_connector(url: str) -> str | None:
    if "slack.com" in url:
        return "slack"
    if "github.com" in url:
        return "github"
    if "figma.com" in url:
        return "figma"
    if "atlassian.net" in url or "jira" in url:
        return "atlassian"
    if "drive.google.com" in url or "docs.google.com" in url:
        return "google_drive"
    if "notion.so" in url:
        return "notion"
    return None


def _extract_source_id(url: str) -> str:
    """Extract a stable, connector-specific ID from a URL."""
    # Slack channel ID from URL
    match = re.search(r"/archives/([A-Z0-9]+)", url)
    if match:
        return match.group(1)
    # GitHub repo slug
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    if match:
        return match.group(1)
    # Figma file key
    match = re.search(r"figma\.com/(?:file|design)/([^/]+)", url)
    if match:
        return match.group(1)
    # Google Drive folder/file ID
    match = re.search(r"(?:folders|d)/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    # Notion page ID
    match = re.search(r"([a-f0-9]{32})", url.replace("-", ""))
    if match:
        return match.group(1)
    # Fallback
    return url


async def _mark_stale_sources(
    discovered_program_ids: set[str],
    discovered_project_urls: set[str],
) -> None:
    """Mark sources as archived for projects that disappeared from program pages."""
    for program_id in discovered_program_ids:
        db_projects = await list_projects_for_program(program_id)
        for project in db_projects:
            if project["notion_hub_url"] not in discovered_project_urls:
                sources = await list_sources_for_project(project["id"])
                for source in sources:
                    await update_source_sync_status(source["id"], "archived")
                    log.info("Archived stale source %s from project %s", source["id"], project["id"])
