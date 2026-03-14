import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route


def create_app() -> Starlette:
    from vgv_rag.server.mcp_server import mcp
    from vgv_rag.config.settings import settings

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "vgv-project-rag"})

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ]
    )


def run():
    from dotenv import load_dotenv
    load_dotenv()
    from vgv_rag.config.settings import settings
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
