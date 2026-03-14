import pytest
import importlib


def test_settings_reads_supabase_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    import vgv_rag.config.settings as mod
    importlib.reload(mod)

    assert mod.settings.supabase_url == "https://test.supabase.co"
    assert mod.settings.port == 3000


def test_settings_optional_connectors_default_none(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.delenv("NOTION_API_TOKEN", raising=False)

    import vgv_rag.config.settings as mod
    importlib.reload(mod)

    assert mod.settings.notion_api_token is None


def test_settings_raises_on_missing_required(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    import vgv_rag.config.settings as mod
    with pytest.raises(Exception):
        importlib.reload(mod)
        _ = mod.settings.supabase_url
