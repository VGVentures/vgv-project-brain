# VGV Project RAG Service

A centralized MCP server that indexes project artifacts from Notion, Slack, GitHub, Figma, Google Drive, and Atlassian into Pinecone, then serves semantic search (with Voyage.ai reranking) to Claude interfaces (Code, Desktop, claude.ai). Supabase handles auth and relational metadata.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Supabase](https://supabase.com) project
- A [Voyage.ai](https://www.voyageai.com) API key
- A [Pinecone](https://www.pinecone.io) account and index

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
| `VOYAGE_API_KEY` | Yes | Voyage.ai API key for embeddings and reranking |
| `PINECONE_API_KEY` | Yes | Pinecone API key |
| `PINECONE_INDEX_NAME` | No | Pinecone index name (default: `vgv-project-rag`) |
| `NOTION_API_TOKEN` | For Notion sync | Internal integration token |
| `SLACK_BOT_TOKEN` | For Slack sync | Bot token (`xoxb-...`) |
| `GITHUB_APP_ID` | For GitHub sync (App) | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | For GitHub sync (App) | PEM-encoded private key |
| `GITHUB_APP_INSTALLATION_ID` | For GitHub sync (App) | Installation ID |
| `GITHUB_PAT` | For GitHub sync (PAT fallback) | Personal access token |
| `FIGMA_API_TOKEN` | For Figma sync | Personal access token |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | For Google Drive sync | Base64-encoded service account JSON key, or path to key file |
| `ATLASSIAN_API_TOKEN` | For Jira sync | API token |
| `ATLASSIAN_EMAIL` | For Jira sync | Service account email |
| `ATLASSIAN_DOMAIN` | For Jira sync | e.g. `yourorg.atlassian.net` |
| `PORT` | No | Server port (default: `3000`) |
| `LOG_LEVEL` | No | Log level (default: `INFO`) |

Supabase, Voyage.ai, and Pinecone credentials are required to start the server. Connector tokens are optional — the service only activates connectors whose credentials are present.

### 3. Set up Pinecone index

Create a Pinecone serverless index named `vgv-project-rag` (or your chosen name) with **1024 dimensions** and **cosine** metric. The service uses namespace-per-project isolation.

### 4. Run database migrations

In the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new), paste and run the migrations from `src/vgv_rag/storage/migrations/` in order:

1. `001_initial_schema.sql` — creates `projects`, `sources`, `project_members`
2. `002_remove_chunks.sql` — removes unused pgvector setup
3. `003_add_programs.sql` — adds `programs` table, program-project relationships, discovery RPC

Vector storage is handled by Pinecone, not Supabase.

If the schema is missing when the service starts, it will log an error with the exact dashboard URL to fix it.

## Running locally

```bash
uv run python -m vgv_rag.main
```

The server starts on `http://localhost:3000`.

- `GET /health` — liveness check
- `/mcp` — MCP SSE endpoint

On startup, the service verifies connectivity to both Supabase and Pinecone.

## Auto-onboarding

The service automatically discovers all programs and projects from the Notion PHT teamspace:

- **On startup + hourly**: crawls Notion `search()` to find program pages, follows project hub links, and upserts everything to Supabase
- **Every 15 minutes**: syncs all discovered sources across all connectors
- Programs and projects are organized hierarchically — program-level content (SOWs, account plans, Slack channels) is searchable by members of any child project

### Manual onboarding (optional)

For one-off imports, the seed script is still available:

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name" \
  --member "you@verygood.ventures"
```

Members can query only their own projects — membership is verified at the application layer before querying Pinecone.

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

- **`search_project_context`** — semantic search across all indexed project artifacts, with Voyage.ai reranking
- **`list_sources`** — show what's indexed for a project, sync status, and any errors
- **`ingest_document`** — manually index a piece of content or a URL

## Running tests

```bash
uv run pytest
```

Tests use mocks for all external services (Supabase, Voyage.ai, Pinecone, connector APIs) and run without any credentials.

## Docker

Build and run with Docker Compose:

```bash
docker-compose up --build
```

The image is lightweight — no local ML models. Embeddings and reranking are handled by the Voyage.ai API.

## Project structure

```
src/vgv_rag/
├── config/settings.py          # Typed env config (pydantic-settings)
├── storage/
│   ├── client.py               # Supabase client singleton (service-role only)
│   ├── supabase_queries.py     # Relational operations (projects, sources, members)
│   ├── pinecone_store.py       # Vector operations (upsert, query, delete)
│   └── migrations/             # SQL migrations
├── processing/
│   ├── embedder.py             # Voyage.ai voyage-4-lite (1024-dim)
│   ├── reranker.py             # Voyage.ai rerank-2-lite with graceful fallback
│   ├── chunker.py              # Per-artifact-type chunking strategies
│   └── metadata.py             # Chunk metadata builder
├── server/
│   ├── mcp_server.py           # FastMCP tool definitions
│   ├── auth.py                 # JWT validation
│   └── tools/                  # Tool handler implementations
├── ingestion/
│   ├── connectors/             # Notion, Slack, GitHub, Figma, Google Drive, Atlassian
│   ├── discovery.py            # Auto-onboarding: crawls Notion, discovers programs/projects
│   ├── program_parser.py       # Parses Notion program pages for project hubs/links
│   ├── project_hub_parser.py   # Reads Notion Hub, discovers sources
│   └── scheduler.py            # APScheduler: hourly discovery + 15-min source sync
└── main.py                     # Starlette app + startup wiring
scripts/
└── seed_project.py             # Project onboarding CLI
```
