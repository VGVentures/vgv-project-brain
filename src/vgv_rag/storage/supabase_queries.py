from __future__ import annotations
import asyncio
from typing import Any
from vgv_rag.storage.client import get_client


async def upsert_project(name: str, notion_hub_url: str, config: dict | None = None) -> str:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").upsert(
            {"name": name, "notion_hub_url": notion_hub_url, "config": config or {}},
            on_conflict="notion_hub_url",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def upsert_source(
    project_id: str, connector: str, source_url: str, source_id: str
) -> str:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("sources").upsert(
            {"project_id": project_id, "connector": connector,
             "source_url": source_url, "source_id": source_id},
            on_conflict="project_id,connector,source_id",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def update_source_sync_status(
    source_id: str, status: str, error: str | None = None
) -> None:
    client = get_client()
    from datetime import datetime, timezone
    payload: dict = {"sync_status": status, "sync_error": error}
    if status == "success":
        payload["last_synced_at"] = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(
        lambda: client.table("sources").update(payload).eq("id", source_id).execute()
    )


async def list_sources_for_project(project_id: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("sources").select("*").eq("project_id", project_id).execute()
    )
    return result.data or []


async def get_project_by_name(name: str) -> dict | None:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").select("*").ilike("name", name).execute()
    )
    return result.data[0] if result.data else None


async def list_projects_for_user(user_email: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("project_members")
            .select("project_id, projects(*)")
            .eq("user_email", user_email)
            .execute()
    )
    return [row["projects"] for row in (result.data or [])]
