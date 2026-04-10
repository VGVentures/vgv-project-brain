import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_upsert_project_returns_id(mock_supabase):
    from vgv_rag.storage.supabase_queries import upsert_project

    mock_supabase.table.return_value.upsert.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-uuid-123"}]
    )

    project_id = await upsert_project(name="Test", notion_hub_url="https://notion.so/abc")
    assert project_id == "proj-uuid-123"


@pytest.mark.asyncio
async def test_upsert_source_inserts_new(mock_supabase):
    from vgv_rag.storage.supabase_queries import upsert_source

    # No existing source found
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    # Insert returns the new source
    mock_supabase.table.return_value.insert.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "src-uuid-456"}]
    )

    source_id = await upsert_source(
        project_id="proj-1", connector="notion",
        source_url="https://notion.so/page", source_id="page-id",
    )
    assert source_id == "src-uuid-456"


@pytest.mark.asyncio
async def test_upsert_source_updates_existing(mock_supabase):
    from vgv_rag.storage.supabase_queries import upsert_source

    # Existing source found
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "src-existing"}]
    )
    # Update returns the source
    mock_supabase.table.return_value.update.return_value.eq.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "src-existing"}]
    )

    source_id = await upsert_source(
        project_id="proj-1", connector="notion",
        source_url="https://notion.so/page", source_id="page-id",
    )
    assert source_id == "src-existing"


@pytest.mark.asyncio
async def test_update_source_sync_status(mock_supabase):
    from vgv_rag.storage.supabase_queries import update_source_sync_status

    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    await update_source_sync_status("src-1", "success")
    mock_supabase.table.assert_called_with("sources")


@pytest.mark.asyncio
async def test_list_sources_for_project(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_sources_for_project

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "src-1", "connector": "notion"}]
    )

    sources = await list_sources_for_project("proj-1")
    assert len(sources) == 1
    assert sources[0]["connector"] == "notion"


@pytest.mark.asyncio
async def test_get_project_by_name(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_project_by_name

    mock_supabase.table.return_value.select.return_value.ilike.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "name": "MyProject"}]
    )

    project = await get_project_by_name("MyProject")
    assert project["id"] == "proj-1"


@pytest.mark.asyncio
async def test_get_project_by_name_not_found(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_project_by_name

    mock_supabase.table.return_value.select.return_value.ilike.return_value.execute.return_value = MagicMock(
        data=[]
    )

    project = await get_project_by_name("NonExistent")
    assert project is None


@pytest.mark.asyncio
async def test_list_projects_for_user(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_projects_for_user

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-1", "projects": {"id": "proj-1", "name": "MyProject"}}]
    )

    projects = await list_projects_for_user("alice@verygood.ventures")
    assert len(projects) == 1
    assert projects[0]["name"] == "MyProject"
