from mcp.server.fastmcp import FastMCP

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
    return "Not yet implemented"


@mcp.tool()
async def list_sources(project: str = "") -> str:
    """Show indexed sources for a project: connector, sync status, last sync time, any errors."""
    return "Not yet implemented"


@mcp.tool()
async def ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    """Manually add a document to the project index."""
    return "Not yet implemented"
