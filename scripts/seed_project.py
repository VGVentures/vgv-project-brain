#!/usr/bin/env python3
"""CLI to onboard a new project from a Notion Project Hub URL."""
import asyncio
import argparse
import dataclasses
from dotenv import load_dotenv
load_dotenv()

from vgv_rag.ingestion.project_hub_parser import parse_project_hub
from vgv_rag.ingestion.connectors.notion import NotionConnector
from vgv_rag.ingestion.connectors.types import Source
from vgv_rag.ingestion.scheduler import sync_source
from vgv_rag.storage.queries import upsert_project, upsert_source
from vgv_rag.storage.client import get_client
from vgv_rag.config.settings import settings


async def run(hub_url: str, name: str, members: list[str]) -> None:
    if not settings.notion_api_token:
        raise SystemExit("NOTION_API_TOKEN is required")

    print(f"Onboarding project: {name}")
    print(f"Hub URL: {hub_url}\n")

    print("1. Parsing Project Hub...")
    config = await parse_project_hub(hub_url, settings.notion_api_token)
    print(f"   Discovered: {dataclasses.asdict(config)}\n")

    print("2. Creating project record...")
    project_id = await upsert_project(
        name=name,
        notion_hub_url=hub_url,
        config=dataclasses.asdict(config),
    )
    print(f"   Project ID: {project_id}\n")

    print("3. Syncing Notion sources...")
    connector = NotionConnector(settings.notion_api_token)
    for url in config.notion_pages:
        source_id_str = url.split("-")[-1][:32]
        source_id = await upsert_source(
            project_id=project_id,
            connector="notion",
            source_url=url,
            source_id=source_id_str,
        )
        source = Source(
            id=source_id, project_id=project_id, connector="notion",
            source_url=url, source_id=source_id_str,
        )
        print(f"   Syncing {url}...")
        await sync_source(source=source, connector=connector)
        print("   Done.")

    if members:
        print("\n4. Adding project members...")
        client = get_client()
        for email in members:
            client.table("project_members").upsert(
                {"project_id": project_id, "user_email": email}
            ).execute()
            print(f"   Added: {email}")

    print("\nProject onboarded successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboard a project from a Notion Project Hub.")
    parser.add_argument("--hub-url", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--member", action="append", default=[], dest="members")
    args = parser.parse_args()
    asyncio.run(run(args.hub_url, args.name, args.members))


if __name__ == "__main__":
    main()
