import asyncio
import logging

log = logging.getLogger(__name__)


async def check_schema(supabase_url: str) -> bool:
    """Returns True if the schema is initialized, False if tables are missing."""
    from vgv_rag.storage.client import get_client
    client = get_client()
    try:
        # Check both core tables exist
        await asyncio.to_thread(
            lambda: client.table("projects").select("id").limit(1).execute()
        )
        await asyncio.to_thread(
            lambda: client.table("programs").select("id").limit(1).execute()
        )
        return True
    except Exception as exc:
        if "PGRST205" in str(exc) or "schema cache" in str(exc):
            return False
        raise
