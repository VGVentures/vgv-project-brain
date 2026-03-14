# src/vgv_rag/main.py
import logging
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from dotenv import load_dotenv


def build_connector_registry():
    from vgv_rag.config.settings import settings
    from vgv_rag.ingestion.connectors.notion import NotionConnector
    from vgv_rag.ingestion.connectors.slack import SlackConnector
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.figma import FigmaConnector
    from vgv_rag.ingestion.connectors.atlassian import AtlassianConnector

    connectors = {}
    if settings.notion_api_token:
        connectors["notion"] = NotionConnector(settings.notion_api_token)
    if settings.slack_bot_token:
        connectors["slack"] = SlackConnector(settings.slack_bot_token)
    if settings.github_pat:
        connectors["github"] = GitHubConnector(settings.github_pat)
    if settings.figma_api_token:
        connectors["figma"] = FigmaConnector(settings.figma_api_token)
    if all([settings.atlassian_api_token, settings.atlassian_email, settings.atlassian_domain]):
        connectors["atlassian"] = AtlassianConnector(
            token=settings.atlassian_api_token,
            email=settings.atlassian_email,
            domain=settings.atlassian_domain,
        )
    return connectors


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "vgv-project-rag"})


def create_app() -> Starlette:
    from vgv_rag.server.mcp_server import mcp
    from vgv_rag.ingestion.scheduler import start_scheduler

    async def on_startup():
        registry = build_connector_registry()
        start_scheduler(registry.get)

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ],
        on_startup=[on_startup],
    )


def run():
    load_dotenv()
    from vgv_rag.config.settings import settings
    logging.basicConfig(level=settings.log_level)
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
