import logging
from vgv_rag.processing.embedder import embed
from vgv_rag.processing.reranker import rerank
from vgv_rag.storage.supabase_queries import (
    list_projects_for_user, get_project_by_name, get_project_by_id,
    list_programs_for_user,
)
from vgv_rag.storage.pinecone_store import query_vectors

log = logging.getLogger(__name__)

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

    # Build namespace list: project + parent program (if any)
    namespaces_to_search = [project_id]

    proj_record = await get_project_by_id(project_id)
    if proj_record and proj_record.get("program_id"):
        namespaces_to_search.append(proj_record["program_id"])

    # If no project specified, also search all accessible programs
    if not project:
        user_programs = await list_programs_for_user(user_email)
        for prog in user_programs:
            if prog["id"] not in namespaces_to_search:
                namespaces_to_search.append(prog["id"])

    # Build metadata filter
    filter_meta: dict | None = None
    if filters:
        filter_meta = {k: v for k, v in filters.items() if v} or None

    # Embed and search across all namespaces
    top_k = min(top_k, 20)
    vector = await embed(query)

    per_ns_candidates = max(top_k, (top_k * RERANK_CANDIDATE_MULTIPLIER) // len(namespaces_to_search))
    all_candidates = []
    for ns in namespaces_to_search:
        try:
            results = await query_vectors(
                namespace=ns,
                embedding=vector,
                top_k=per_ns_candidates,
                filters=filter_meta,
            )
            all_candidates.extend(results)
        except Exception as exc:
            log.warning("Search failed for namespace %s: %s", ns, exc)

    if not all_candidates:
        return "No relevant results found."

    # Rerank the merged candidate set
    results = await rerank(query, all_candidates, top_k=top_k)

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
