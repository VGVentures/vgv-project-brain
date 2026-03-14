from vgv_rag.processing.embedder import embed
from vgv_rag.storage.queries import search_chunks, list_projects_for_user, get_project_by_name


async def handle_search_project_context(
    query: str,
    user_email: str,
    project: str = "",
    filters: dict | None = None,
    top_k: int = 5,
) -> str:
    # Resolve project
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

    # Build metadata filter
    filter_meta: dict | None = None
    if filters:
        filter_meta = {k: v for k, v in filters.items() if v} or None

    # Embed and search
    vector = await embed(query)
    chunks = await search_chunks(
        embedding=vector,
        project_id=project_id,
        top_k=min(top_k, 20),
        filter_metadata=filter_meta,
    )

    if not chunks:
        return "No relevant results found."

    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        pct = f"{c['similarity'] * 100:.0f}%"
        lines.append(f"--- Result {i} (similarity: {pct}) ---")
        lines.append(f"Source: {meta.get('source_tool', 'unknown')} | Type: {meta.get('artifact_type', 'unknown')}")
        if meta.get("source_url"):
            lines.append(f"URL: {meta['source_url']}")
        if meta.get("author"):
            lines.append(f"Author: {meta['author']}")
        if meta.get("date"):
            lines.append(f"Date: {meta['date']}")
        lines.append("")
        lines.append(c["content"])

    return "\n".join(lines)
