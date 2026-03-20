# VGV Project RAG Service

A centralized MCP server that indexes project artifacts from Notion, Slack, GitHub, Figma, and Atlassian into Supabase pgvector, then serves semantic search to Claude interfaces (Code, Desktop, claude.ai).

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Supabase](https://supabase.com) project

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key (server-side only) |
| `SUPABASE_ANON_KEY` | Yes | Anon key (used for auth flows) |
| `NOTION_API_TOKEN` | For Notion sync | Internal integration token |
| `SLACK_BOT_TOKEN` | For Slack sync | Bot token (`xoxb-...`) |
| `GITHUB_PAT` | For GitHub sync | Personal access token |
| `FIGMA_API_TOKEN` | For Figma sync | Personal access token |
| `ATLASSIAN_API_TOKEN` | For Jira sync | API token |
| `ATLASSIAN_EMAIL` | For Jira sync | Service account email |
| `ATLASSIAN_DOMAIN` | For Jira sync | e.g. `yourorg.atlassian.net` |
| `PORT` | No | Server port (default: `3000`) |
| `LOG_LEVEL` | No | Log level (default: `INFO`) |

Only the Supabase variables are required to start the server. Connector tokens are optional — the service only activates connectors whose credentials are present.

### 3. Run database migrations

In the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new), paste and run the contents of `src/vgv_rag/storage/migrations/001_initial_schema.sql`.

This creates the `projects`, `sources`, `chunks`, and `project_members` tables, enables the `pgvector` extension, creates the HNSW index, and sets up Row Level Security.

If the schema is missing when the service starts, it will log an error with the exact dashboard URL to fix it.

## Running locally

```bash
uv run python -m vgv_rag.main
```

The server starts on `http://localhost:3000`.

- `GET /health` — liveness check
- `/mcp` — MCP SSE endpoint

## Onboarding a project

The seed script reads a Notion Project Hub page, discovers all linked sources (Slack channels, GitHub repos, Figma files, Jira boards), creates the project record in Supabase, and runs an initial Notion sync.

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name" \
  --member "you@verygood.ventures"
```

Repeat `--member` for each team member to add. Members can query only their own projects via Row Level Security.

## Connecting to Claude

Add to your Claude MCP config (`~/.claude/claude_desktop_config.json` or equivalent):

```json
{
  "mcpServers": {
    "vgv-project-rag": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

Three tools become available:

- **`search_project_context`** — semantic search across all indexed project artifacts
- **`list_sources`** — show what's indexed for a project, sync status, and any errors
- **`ingest_document`** — manually index a piece of content or a URL

## Running tests

```bash
uv run pytest
```

Tests use mocks for all external services (Supabase, connector APIs, embedding model) and run without any credentials.

## Docker

Build and run with Docker Compose:

```bash
docker-compose up --build
```

The sentence-transformer model (~90MB) is downloaded on first run and cached in a named volume so subsequent starts are fast.

## Project structure

```
src/vgv_rag/
├── config/settings.py          # Typed env config (pydantic-settings)
├── storage/
│   ├── client.py               # Supabase client singleton
│   ├── queries.py              # Async query functions
│   └── migrations/             # SQL migrations
├── processing/
│   ├── embedder.py             # sentence-transformers all-MiniLM-L6-v2
│   ├── chunker.py              # Per-artifact-type chunking strategies
│   └── metadata.py             # Chunk metadata builder
├── server/
│   ├── mcp_server.py           # FastMCP tool definitions
│   ├── auth.py                 # JWT validation
│   └── tools/                  # Tool handler implementations
├── ingestion/
│   ├── connectors/             # Notion, Slack, GitHub, Figma, Atlassian
│   ├── project_hub_parser.py   # Reads Notion Hub, discovers sources
│   └── scheduler.py            # APScheduler cron-based sync
└── main.py                     # Starlette app + startup wiring
scripts/
└── seed_project.py             # Project onboarding CLI
```
