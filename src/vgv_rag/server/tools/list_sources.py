# src/vgv_rag/server/tools/list_sources.py
from vgv_rag.storage.queries import list_sources_for_project, get_project_by_name, list_projects_for_user


async def handle_list_sources(project: str, user_email: str) -> str:
    selected_project_name = None
    if project:
        proj = await get_project_by_name(project)
        if not proj:
            return f"Project not found: {project}"
        project_id = proj["id"]
    else:
        projects = await list_projects_for_user(user_email)
        if not projects:
            return "No projects found for your account."
        project_id = projects[0]["id"]
        selected_project_name = projects[0].get("name", project_id)

    sources = await list_sources_for_project(project_id)
    if not sources:
        if selected_project_name:
            return f"No sources indexed yet for project: {selected_project_name}"
        return "No sources indexed yet for this project."

    lines = []
    for s in sources:
        line = f"• [{s['connector']}] {s['source_url']}\n  Status: {s['sync_status']} | Last sync: {s.get('last_synced_at') or 'never'}"
        if s.get("sync_error"):
            line += f"\n  Error: {s['sync_error']}"
        lines.append(line)

    result = "\n\n".join(lines)
    if selected_project_name:
        result = f"(Showing sources for project: {selected_project_name})\n\n" + result
    return result
