from __future__ import annotations
import asyncio
from typing import Any
from vgv_rag.storage.client import get_client


async def upsert_project(
    name: str, notion_hub_url: str, config: dict | None = None, program_id: str | None = None,
) -> str:
    client = get_client()
    payload: dict[str, Any] = {"name": name, "notion_hub_url": notion_hub_url, "config": config or {}}
    if program_id:
        payload["program_id"] = program_id
    result = await asyncio.to_thread(
        lambda: client.table("projects").upsert(
            payload,
            on_conflict="notion_hub_url",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def upsert_source(
    connector: str, source_url: str, source_id: str,
    project_id: str | None = None, program_id: str | None = None,
) -> str:
    client = get_client()
    # PostgREST can't use COALESCE-based indexes for on_conflict.
    # Use select-then-insert/update to handle the composite unique constraint.
    owner_id = project_id or program_id
    owner_col = "project_id" if project_id else "program_id"

    existing = await asyncio.to_thread(
        lambda: client.table("sources")
            .select("id")
            .eq(owner_col, owner_id)
            .eq("connector", connector)
            .eq("source_id", source_id)
            .execute()
    )

    payload: dict[str, Any] = {
        "connector": connector, "source_url": source_url, "source_id": source_id,
    }
    if project_id:
        payload["project_id"] = project_id
    if program_id:
        payload["program_id"] = program_id

    if existing.data:
        # Update existing source
        result = await asyncio.to_thread(
            lambda: client.table("sources")
                .update(payload)
                .eq("id", existing.data[0]["id"])
                .select("id")
                .execute()
        )
    else:
        # Insert new source
        result = await asyncio.to_thread(
            lambda: client.table("sources")
                .insert(payload)
                .select("id")
                .execute()
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


async def upsert_program(name: str, notion_page_url: str, config: dict | None = None) -> str:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("programs").upsert(
            {"name": name, "notion_page_url": notion_page_url, "config": config or {}},
            on_conflict="notion_page_url",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def get_program_by_notion_url(url: str) -> dict | None:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("programs").select("*").eq("notion_page_url", url).execute()
    )
    return result.data[0] if result.data else None


async def list_all_programs() -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("programs").select("*").execute()
    )
    return result.data or []


async def list_projects_for_program(program_id: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").select("*").eq("program_id", program_id).execute()
    )
    return result.data or []


async def list_programs_for_user(user_email: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.rpc(
            "list_programs_for_user",
            {"p_user_email": user_email},
        ).execute()
    )
    return result.data or []


async def list_sources_for_program(program_id: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("sources").select("*").eq("program_id", program_id).execute()
    )
    return result.data or []


async def get_project_by_id(project_id: str) -> dict | None:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").select("*").eq("id", project_id).execute()
    )
    return result.data[0] if result.data else None
