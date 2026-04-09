from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        from vgv_rag.config.settings import settings
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client
