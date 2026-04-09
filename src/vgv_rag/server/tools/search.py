from vgv_rag.processing.embedder import embed
from vgv_rag.processing.reranker import rerank
from vgv_rag.storage.supabase_queries import list_projects_for_user, get_project_by_name
from vgv_rag.storage.pinecone_store import query_vectors

RERANK_CANDIDATE_MULTIPLIER = 4


async def handle_search_project_context(
    query: str,
    user_email: str,
    project: str = "",
    filters: dict | None = None,
    top_k: int = 5,
) -> str:
    # Get user's projects (used for both auto-detection and membership verification)
    user_projects = await list_projects_for_user(user_email)

    # Resolve project
    if project:
        proj = await get_project_by_name(project)
        if not proj:
            return f"Project not found: {project}"
        project_id = proj["id"]
    else:
        if not user_projects:
            return "No projects found for your account."
        project_id = user_projects[0]["id"]

    # Verify membership
    if project_id not in [p["id"] for p in user_projects]:
        return f"Not authorized: you are not a member of this project."

    # Build metadata filter
    filter_meta: dict | None = None
    if filters:
        filter_meta = {k: v for k, v in filters.items() if v} or None

    # Embed and search
    top_k = min(top_k, 20)
    vector = await embed(query)
    candidates = await query_vectors(
        namespace=project_id,
        embedding=vector,
        top_k=top_k * RERANK_CANDIDATE_MULTIPLIER,
        filters=filter_meta,
    )

    if not candidates:
        return "No relevant results found."

    # Rerank
    results = await rerank(query, candidates, top_k=top_k)

    if not results:
        return "No relevant results found."

    lines = []
    for i, c in enumerate(results, 1):
        meta = c.get("metadata", {})
        score = c.get("relevance_score", c.get("score", 0))
        pct = f"{score * 100:.0f}%"
        lines.append(f"--- Result {i} (relevance: {pct}) ---")
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
