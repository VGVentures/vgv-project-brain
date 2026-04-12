# VGV Project RAG Service

A centralized MCP server that indexes project artifacts from Notion, Slack, GitHub, Figma, Google Drive, and Atlassian into Pinecone, then serves semantic search (with Voyage.ai reranking) to Claude interfaces (Code, Desktop, claude.ai). Supabase handles auth and relational metadata.

Programs and projects are auto-discovered by crawling the Notion PHT teamspace — no manual onboarding or admin UI needed.

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/VGVentures/vgv-project-brain.git
cd vgv-project-brain
uv sync

# 2. Run tests (no credentials needed)
uv run pytest

# 3. Configure and run (requires credentials — see below)
cp .env.example .env
# Edit .env with your credentials...
uv run python -m vgv_rag.main
```

## Local development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Install dependencies

```bash
uv sync
```

This installs both production and dev dependencies (pytest, pytest-asyncio, pytest-mock, respx).

### Running tests

Tests use mocks for all external services and run without any credentials or network access.

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_discovery.py

# Run a specific test by name
uv run pytest -k "test_search_includes_program_namespace"

# Run tests and stop on first failure
uv run pytest -x

# Run with short traceback
uv run pytest -x -q
```

#### Test structure

```
tests/
├── conftest.py                       # Shared fixtures (mock_supabase, env loading)
├── connectors/
│   ├── test_atlassian.py
│   ├── test_figma.py
│   ├── test_github.py                # GitHub App auth + PAT tests
│   ├── test_google_drive.py
│   ├── test_notion.py
│   └── test_slack.py
├── test_auth.py
├── test_chunker.py
├── test_discovery.py                 # Auto-onboarding discovery engine
├── test_embedder.py
├── test_pinecone_store.py
├── test_program_parser.py            # Notion program page parsing
├── test_project_hub_parser.py
├── test_reranker.py
├── test_scheduler.py
├── test_search_tool.py               # Multi-namespace search
├── test_settings.py
├── test_supabase_queries.py
├── test_supabase_queries_programs.py  # Program CRUD operations
└── test_tools.py
```

All tests use `pytest-mock` for patching and `pytest-asyncio` for async test support. The `asyncio_mode = "auto"` setting in `pyproject.toml` means you don't need `@pytest.mark.asyncio` decorators (though they're included for clarity).

### Running the server locally

The server requires credentials for Supabase, Voyage.ai, and Pinecone. Connector tokens are optional.

```bash
cp .env.example .env
# Edit .env — at minimum fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
# SUPABASE_ANON_KEY, VOYAGE_API_KEY, PINECONE_API_KEY
```

Then start:

```bash
uv run python -m vgv_rag.main
```

The server starts on `http://localhost:3000`:

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check — returns `{"status": "ok"}` |
| `/mcp` | MCP SSE endpoint for Claude interfaces |

On startup the service:
1. Validates Supabase schema (logs error with SQL Editor URL if tables missing)
2. Verifies Pinecone index connectivity
3. Initializes connectors for all configured credentials
4. Starts the sync scheduler (discovery + source sync)

### Connecting Claude to your local server

Add to your Claude MCP config:

**Claude Code** (`~/.claude.json` or project `.mcp.json`):
```json
{
  "mcpServers": {
    "vgv-project-rag": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "vgv-project-rag": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

Three MCP tools become available:

- **`search_project_context`** — semantic search across indexed project artifacts with Voyage.ai reranking
- **`list_sources`** — show what's indexed for a project, sync status, and errors
- **`ingest_document`** — manually index content or a URL

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key (server-side only, never expose to clients) |
| `SUPABASE_ANON_KEY` | Yes | Anon key (used for client auth flows) |
| `VOYAGE_API_KEY` | Yes | Voyage.ai API key for embeddings and reranking |
| `PINECONE_API_KEY` | Yes | Pinecone API key |
| `PINECONE_INDEX_NAME` | No | Index name (default: `vgv-project-rag`) |
| `NOTION_API_TOKEN` | For Notion sync + auto-discovery | Internal integration token |
| `SLACK_BOT_TOKEN` | For Slack sync | Bot token (`xoxb-...`) |
| `GITHUB_APP_ID` | For GitHub sync (App) | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | For GitHub sync (App) | PEM-encoded private key |
| `GITHUB_APP_INSTALLATION_ID` | For GitHub sync (App) | Installation ID |
| `GITHUB_PAT` | For GitHub sync (PAT fallback) | Personal access token |
| `FIGMA_API_TOKEN` | For Figma sync | Personal access token |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | For Google Drive sync | Base64-encoded JSON key, or file path |
| `ATLASSIAN_API_TOKEN` | For Jira sync | API token |
| `ATLASSIAN_EMAIL` | For Jira sync | Service account email |
| `ATLASSIAN_DOMAIN` | For Jira sync | e.g. `yourorg.atlassian.net` |
| `PORT` | No | Server port (default: `3000`) |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |

Supabase, Voyage.ai, and Pinecone are required to start. Connectors activate only when their credentials are present.

## Database setup

Run migrations in the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new), in order:

1. `src/vgv_rag/storage/migrations/001_initial_schema.sql` — `projects`, `sources`, `project_members` tables
2. `src/vgv_rag/storage/migrations/002_remove_chunks.sql` — removes unused pgvector setup
3. `src/vgv_rag/storage/migrations/003_add_programs.sql` — `programs` table, program-project FKs, discovery RPC

Vector storage is in Pinecone (namespace-per-project + namespace-per-program), not Supabase.

## Auto-onboarding

The service automatically discovers programs and projects from the Notion PHT teamspace:

- **On startup + hourly**: crawls Notion `search()` to find program pages (identified by a "Project Hubs" heading), follows project hub links, upserts everything to Supabase
- **Every 15 minutes**: syncs all discovered sources across all active connectors
- Programs and projects are hierarchical — program-level content (SOWs, account plans, Slack channels) is searchable by members of any child project
- If a project disappears from a program page, its sources are marked `archived` (vectors preserved, not synced)

### Manual onboarding (optional)

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name" \
  --member "you@verygood.ventures" \
  --program-url "https://www.notion.so/verygoodventures/ProgramPage-def456"  # optional
```

## Docker

### Build and run locally

```bash
docker-compose up --build
```

### Build image only

```bash
docker build -t vgv-project-rag .
docker run --env-file .env -p 3000:3000 vgv-project-rag
```

The image is ~150MB — no local ML models. Embeddings and reranking use the Voyage.ai API.

### Verify

```bash
curl http://localhost:3000/health
# {"status":"ok","service":"vgv-project-rag"}
```

## Production deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full production deployment guide covering:

- External account setup (Supabase, Voyage.ai, Pinecone, Google SSO)
- All connector credential setup (Notion, Slack, GitHub App, Figma, Google Drive, Jira)
- VPS (Docker Compose) and Google Cloud Run deployment
- Upgrading existing deployments
- Monitoring and troubleshooting

## Project structure

```
src/vgv_rag/
├── config/settings.py          # Typed env config (pydantic-settings)
├── storage/
│   ├── client.py               # Supabase client singleton (service-role only)
│   ├── supabase_queries.py     # Relational operations (programs, projects, sources, members)
│   ├── pinecone_store.py       # Vector operations (upsert, query, delete)
│   ├── migrate.py              # Schema verification on startup
│   └── migrations/             # SQL migrations (run manually in Supabase SQL Editor)
├── processing/
│   ├── embedder.py             # Voyage.ai voyage-4-lite (1024-dim)
│   ├── reranker.py             # Voyage.ai rerank-2-lite with graceful fallback
│   ├── chunker.py              # Per-artifact-type chunking strategies
│   └── metadata.py             # Chunk metadata builder
├── server/
│   ├── mcp_server.py           # FastMCP tool definitions
│   ├── auth.py                 # JWT validation via Supabase Auth
│   └── tools/                  # search, list_sources, ingest handlers
├── ingestion/
│   ├── connectors/             # Notion, Slack, GitHub, Figma, Google Drive, Atlassian
│   │   └── types.py            # RawDocument, Source, ProjectConfig, ProgramConfig
│   ├── discovery.py            # Auto-onboarding: crawls Notion for programs/projects
│   ├── program_parser.py       # Parses Notion program pages
│   ├── project_hub_parser.py   # Parses Notion project hub pages
│   └── scheduler.py            # APScheduler: hourly discovery + 15-min source sync
└── main.py                     # Starlette app, connector registry, startup wiring
scripts/
└── seed_project.py             # Manual project onboarding CLI
```
