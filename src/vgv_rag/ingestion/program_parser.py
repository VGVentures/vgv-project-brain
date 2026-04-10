import asyncio
from notion_client import Client
from vgv_rag.ingestion.connectors.types import ProgramConfig
from vgv_rag.ingestion.project_hub_parser import _extract_page_id, _extract_urls


async def parse_program_page(page_url: str, notion_token: str) -> ProgramConfig | None:
    """Parse a Notion program page. Returns None if the page is not a program page."""
    client = Client(auth=notion_token)
    page_id = _extract_page_id(page_url)

    blocks = await asyncio.to_thread(
        lambda: client.blocks.children.list(block_id=page_id)
    )

    config = ProgramConfig()
    found_project_hubs = False
    current_section: str | None = None

    for block in blocks.get("results", []):
        block_type = block.get("type", "")
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text).lower()

        if block_type.startswith("heading"):
            if "project hubs" in text:
                found_project_hubs = True
                current_section = "project_hubs"
            elif "quick links" in text:
                current_section = "quick_links"
            elif "communication channels" in text:
                current_section = "communication_channels"
            else:
                current_section = None
            continue

        if current_section:
            urls = _extract_urls(block)
            if current_section == "project_hubs":
                config.project_hub_urls.extend(urls)
            elif current_section == "quick_links":
                config.quick_links.extend(urls)
            elif current_section == "communication_channels":
                config.communication_channels.extend(urls)

    if not found_project_hubs:
        return None

    return config
