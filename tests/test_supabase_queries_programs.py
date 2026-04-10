import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_upsert_program_returns_id(mock_supabase):
    from vgv_rag.storage.supabase_queries import upsert_program

    mock_supabase.table.return_value.upsert.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "prog-uuid-1"}]
    )

    program_id = await upsert_program(
        name="Scooter's Coffee", notion_page_url="https://notion.so/scooters"
    )
    assert program_id == "prog-uuid-1"
    mock_supabase.table.assert_called_with("programs")


@pytest.mark.asyncio
async def test_upsert_program_with_config(mock_supabase):
    from vgv_rag.storage.supabase_queries import upsert_program

    mock_supabase.table.return_value.upsert.return_value.select.return_value.execute.return_value = MagicMock(
        data=[{"id": "prog-uuid-2"}]
    )

    config = {"project_hub_urls": ["https://notion.so/hub1"]}
    program_id = await upsert_program(
        name="Test Program", notion_page_url="https://notion.so/test", config=config
    )
    assert program_id == "prog-uuid-2"

    call_args = mock_supabase.table.return_value.upsert.call_args[0][0]
    assert call_args["config"] == config


@pytest.mark.asyncio
async def test_get_program_by_notion_url_found(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_program_by_notion_url

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "prog-1", "name": "Scooters"}]
    )

    program = await get_program_by_notion_url("https://notion.so/scooters")
    assert program["id"] == "prog-1"


@pytest.mark.asyncio
async def test_get_program_by_notion_url_not_found(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_program_by_notion_url

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    program = await get_program_by_notion_url("https://notion.so/nonexistent")
    assert program is None


@pytest.mark.asyncio
async def test_list_all_programs(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_all_programs

    mock_supabase.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "prog-1", "name": "Program A"},
            {"id": "prog-2", "name": "Program B"},
        ]
    )

    programs = await list_all_programs()
    assert len(programs) == 2
    assert programs[0]["name"] == "Program A"


@pytest.mark.asyncio
async def test_list_all_programs_empty(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_all_programs

    mock_supabase.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[]
    )

    programs = await list_all_programs()
    assert programs == []


@pytest.mark.asyncio
async def test_list_projects_for_program(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_projects_for_program

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "proj-1", "name": "Project A", "program_id": "prog-1"},
            {"id": "proj-2", "name": "Project B", "program_id": "prog-1"},
        ]
    )

    projects = await list_projects_for_program("prog-1")
    assert len(projects) == 2


@pytest.mark.asyncio
async def test_list_programs_for_user(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_programs_for_user

    # Simulates: project_members → projects → programs join
    mock_supabase.rpc.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "prog-1", "name": "Program A"},
        ]
    )

    programs = await list_programs_for_user("alice@verygood.ventures")
    assert len(programs) == 1
    assert programs[0]["name"] == "Program A"


@pytest.mark.asyncio
async def test_list_sources_for_program(mock_supabase):
    from vgv_rag.storage.supabase_queries import list_sources_for_program

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "src-1", "connector": "slack", "program_id": "prog-1"},
        ]
    )

    sources = await list_sources_for_program("prog-1")
    assert len(sources) == 1
    assert sources[0]["connector"] == "slack"


@pytest.mark.asyncio
async def test_get_project_by_id_found(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_project_by_id

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "name": "MyProject", "program_id": "prog-1"}]
    )

    project = await get_project_by_id("proj-1")
    assert project["program_id"] == "prog-1"


@pytest.mark.asyncio
async def test_get_project_by_id_not_found(mock_supabase):
    from vgv_rag.storage.supabase_queries import get_project_by_id

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    project = await get_project_by_id("nonexistent")
    assert project is None
