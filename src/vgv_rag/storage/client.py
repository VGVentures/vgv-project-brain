from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        from vgv_rag.config.settings import settings
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def get_user_client(jwt: str) -> Client:
    """User-scoped client that respects Row Level Security."""
    from vgv_rag.config.settings import settings
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options={"headers": {"Authorization": f"Bearer {jwt}"}},
    )
