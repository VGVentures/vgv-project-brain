# src/vgv_rag/server/mcp_server.py
from mcp.server.fastmcp import FastMCP
from vgv_rag.server.tools.search import handle_search_project_context
from vgv_rag.server.tools.list_sources import handle_list_sources
from vgv_rag.server.tools.ingest import handle_ingest_document

mcp = FastMCP("vgv-project-rag")

DEV_EMAIL = "dev@verygood.ventures"


@mcp.tool()
async def search_project_context(
    query: str,
    project: str = "",
    artifact_type: str = "",
    source_tool: str = "",
    top_k: int = 5,
) -> str:
    """Search project knowledge across Notion, Slack, GitHub, Figma, and Jira. Returns relevant chunks with source links."""
    filters = {"artifact_type": artifact_type, "source_tool": source_tool}
    return await handle_search_project_context(
        query=query, user_email=DEV_EMAIL, project=project, filters=filters, top_k=top_k,
    )


@mcp.tool()
async def list_sources(project: str = "") -> str:
    """Show indexed sources for a project: connector, sync status, last sync time, any errors."""
    return await handle_list_sources(project=project, user_email=DEV_EMAIL)


@mcp.tool()
async def ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    """Manually add a document to the project index. Provide either content or a URL to fetch."""
    return await handle_ingest_document(project=project, content=content, url=url, artifact_type=artifact_type)
