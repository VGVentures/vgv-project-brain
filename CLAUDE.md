# VGV Project RAG Service — Implementation Spec

> Drop this file into a bare git repo and use it as the CLAUDE.md for Claude Code to stand up the service.

## What This Is

A centralized MCP server that indexes project artifacts from Notion, Slack, GitHub, Figma, Google Drive, and Atlassian (Jira) into a Pinecone vector database, then serves semantic search results (with Voyage.ai reranking) to any Claude interface (Code, Desktop, Cowork, claude.ai). Supabase handles auth and relational metadata. Team members authenticate via Google Workspace SSO through Supabase Auth. Project configuration is pulled from VGV's existing Notion Project Hub pages — no admin UI needed.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Claude Interfaces (consumers)                          │
│  Claude Code · Desktop · Cowork · claude.ai             │
│  Connect via MCP URL in settings                        │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP (SSE or stdio-over-HTTP)
                       ▼
┌─────────────────────────────────────────────────────────┐
│  VGV Project RAG Service                                │
│  (Docker container on VPS or Cloud Run)                 │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ MCP Server   │  │ Ingestion    │  │ Voyage.ai     │  │
│  │ (query +     │  │ Scheduler    │  │ Embeddings    │  │
│  │  auth)       │  │ (cron-based) │  │ + Reranker    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────┘  │
│         │                │                              │
│         ▼                ▼                              │
│  ┌─────────────────────────────────┐                    │
│  │ Connector Layer                 │                    │
│  │ Notion · Slack · GitHub ·       │                    │
│  │ Figma · Google Drive ·          │                    │
│  │ Atlassian                       │                    │
│  └─────────────────────────────────┘                    │
└──────────┬──────────────────────────┬───────────────────┘
           │ SQL (relational)         │ Vector ops
           ▼                          ▼
┌──────────────────────┐  ┌───────────────────────────────┐
│  Supabase            │  │  Pinecone                     │
│  PostgreSQL (auth,   │  │  Serverless vector DB         │
│  projects, sources,  │  │  (namespace-per-project       │
│  members)            │  │   isolation)                  │
│  Supabase Auth +     │  │                               │
│  Google SSO          │  │                               │
└──────────────────────┘  └───────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12 | MCP SDK supports Python; strong ecosystem for ML/embedding libraries |
| MCP Server | `mcp[cli]` | Official MCP SDK for building servers |
| Vector DB | Pinecone (serverless) | Managed vector DB with namespace isolation, metadata filtering, scales to zero |
| Relational DB | Supabase (PostgreSQL) | Auth, projects, sources, members — no vector storage |
| Auth | Supabase Auth with Google OAuth | VGV Google Workspace SSO; no custom auth to build |
| Embeddings | Voyage.ai (`voyage-4-lite`, 1024-dim) | Cloud API, high-quality embeddings, asymmetric query/document types |
| Reranking | Voyage.ai (`rerank-2-lite`) | Improves result relevance; graceful fallback on failure |
| Connectors | Notion API, Slack API, GitHub API, Figma API, Google Drive API, Atlassian API | Direct API integrations; credentials stored as env vars |
| Deployment | Docker | Runs on VPS (Hetzner/DO/Vultr) or Google Cloud Run |

## Project Structure

```
vgv-project-rag/
├── CLAUDE.md                           ← This file (project instructions)
├── Dockerfile
├── docker-compose.yml                  ← For local dev and VPS deployment
├── pyproject.toml
├── .env.example                        ← Template for required env vars
├── src/
│   └── vgv_rag/
│       ├── main.py                    ← Entry point: starts MCP server + scheduler
│       ├── server/
│       │   ├── mcp_server.py          ← MCP tool definitions and handlers
│       │   ├── auth.py                ← Supabase Auth middleware (Google SSO)
│       │   └── tools/
│       │       ├── search.py          ← search_project_context handler
│       │       ├── list_sources.py    ← list_sources handler
│       │       └── ingest.py          ← ingest_document handler
│       ├── ingestion/
│       │   ├── scheduler.py           ← Cron-based sync orchestrator
│       │   ├── project_hub_parser.py  ← Reads Notion Project Hub, extracts source URLs
│       │   └── connectors/
│       │       ├── notion.py          ← Notion API: pages, databases, meeting notes
│       │       ├── slack.py           ← Slack API: channel messages, threads
│       │       ├── github.py          ← GitHub API: PRs, issues, ADRs, README
│       │       ├── figma.py           ← Figma API: component metadata, tokens
│       │       ├── google_drive.py    ← Google Drive API: Docs, Slides, PDFs
│       │       └── atlassian.py       ← Jira API: issues, sprints, comments
│       ├── processing/
│       │   ├── chunker.py             ← Semantic chunking by document type
│       │   ├── embedder.py            ← Voyage.ai voyage-4-lite embeddings
│       │   ├── reranker.py            ← Voyage.ai rerank-2-lite reranking
│       │   └── metadata.py            ← Metadata extraction and tagging
│       ├── storage/
│       │   ├── client.py              ← Supabase client (service-role only)
│       │   ├── supabase_queries.py    ← Relational operations (projects, sources, members)
│       │   ├── pinecone_store.py      ← Vector operations (upsert, query, delete)
│       │   └── migrations/
│       │       ├── 001_initial_schema.sql ← Tables, indexes
│       │       └── 002_remove_chunks.sql  ← Remove pgvector chunks table
│       └── config/
│           └── settings.py            ← Typed env var access via pydantic-settings
├── scripts/
│   └── seed_project.py                ← CLI to onboard a project by Hub URL
└── tests/
    └── ...
```

## Supabase Setup

### Database Schema

```sql
-- Projects table (discovered from Notion Project Hubs)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_hub_url TEXT NOT NULL UNIQUE,
    notion_pht_url TEXT,
    config JSONB DEFAULT '{}'::jsonb,        -- Parsed Helpful Links (connector configs)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Source tracking (what's been indexed, when)
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    connector TEXT NOT NULL,                  -- 'notion' | 'slack' | 'github' | 'figma' | 'google_drive' | 'atlassian'
    source_url TEXT NOT NULL,                 -- Original URL from Project Hub
    source_id TEXT NOT NULL,                  -- Connector-specific ID (channel ID, repo slug, etc.)
    last_synced_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'pending',       -- 'pending' | 'syncing' | 'success' | 'error'
    sync_error TEXT,
    UNIQUE(project_id, connector, source_id)
);

-- Project team membership (for access control)
CREATE TABLE project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_email TEXT NOT NULL,                -- @verygood.ventures email
    role TEXT DEFAULT 'member',              -- 'admin' | 'member'
    UNIQUE(project_id, user_email)
);

-- NOTE: Vector storage (chunks + embeddings) is in Pinecone, not Supabase.
-- Pinecone uses namespace-per-project isolation.
-- Vector IDs follow {source_id}:{chunk_index} scheme.
-- Chunk content is stored in Pinecone metadata alongside embeddings.
-- Project membership is verified at the application layer before querying Pinecone.
```

### Supabase Auth Configuration

1. In Supabase Dashboard > Authentication > Providers, enable **Google** provider
2. Set the Google OAuth Client ID and Secret (from Google Cloud Console, using VGV's Google Workspace)
3. Under URL Configuration, set the redirect URL to the service's callback endpoint
4. Restrict signups to `@verygood.ventures` email domain

The auth flow from a user's perspective:
1. User adds the MCP URL to their Claude config
2. On first query, the MCP server returns a `401` with a Supabase Auth URL
3. User clicks the URL, authenticates with their VGV Google account
4. Supabase issues a JWT; the MCP client caches it
5. Subsequent queries include the JWT; the server validates it and verifies project membership before querying Pinecone

## MCP Server

### Tools Exposed

```typescript
// Tool: search_project_context
// Semantic search across the authenticated user's project(s)
{
  name: "search_project_context",
  description: "Search project knowledge across Notion, Slack, GitHub, Figma, and Jira. Returns relevant chunks with source links.",
  inputSchema: {
    type: "object",
    properties: {
      query: { type: "string", description: "Natural language search query" },
      project: { type: "string", description: "Project name (optional — auto-detected from CLAUDE.md project identifier if omitted)" },
      filters: {
        type: "object",
        properties: {
          artifact_type: { type: "string", description: "Filter by type: meeting_note, prd, story, design_spec, slack_thread, pr, adr, issue" },
          source_tool: { type: "string", description: "Filter by source: notion, slack, github, figma, atlassian" },
          phase: { type: "string", description: "Filter by project phase: pre-sales, design, sprint-1, etc." },
          after: { type: "string", description: "ISO date — only chunks after this date" },
          before: { type: "string", description: "ISO date — only chunks before this date" }
        }
      },
      top_k: { type: "number", description: "Number of results (default: 5, max: 20)" }
    },
    required: ["query"]
  }
}

// Tool: list_sources
// Show what's indexed for the current project
{
  name: "list_sources",
  description: "Show indexed sources for a project: what's connected, last sync time, any errors.",
  inputSchema: {
    type: "object",
    properties: {
      project: { type: "string", description: "Project name (optional)" }
    }
  }
}

// Tool: ingest_document
// Manually trigger ingestion of a specific URL or text
{
  name: "ingest_document",
  description: "Manually add a document to the project index. Use for ad-hoc content not covered by automatic sync.",
  inputSchema: {
    type: "object",
    properties: {
      project: { type: "string", description: "Project name" },
      content: { type: "string", description: "Text content to index (if providing directly)" },
      url: { type: "string", description: "URL to fetch and index (Notion page, Google Doc, etc.)" },
      artifact_type: { type: "string", description: "Type tag for the content" }
    },
    required: ["project"]
  }
}
```

### Query Flow

```
1. User query arrives via MCP with JWT
2. Validate JWT via Supabase Auth
3. Extract user email from JWT
4. Look up user's project memberships
5. If project specified in query, verify membership (security check)
6. If project omitted, auto-detect from context (CLAUDE.md project identifier)
7. Embed query via Voyage.ai (input_type="query", 1024-dim)
8. Query Pinecone (namespace=project_id, top_k * 4 candidates, metadata filters)
9. Rerank candidates via Voyage.ai rerank-2-lite → return top_k results
10. Format results with metadata and source URLs
```

## Ingestion Layer

### Project Hub Parser

The Project Hub parser is the key piece that eliminates manual configuration.

```
Input: Notion Project Hub URL (or PHT entry URL that links to the Hub)
Output: A structured config object with connector-specific source IDs

Steps:
1. Fetch the Project Hub page via Notion API
2. Parse the "Helpful Links" section
3. For each link category, extract URLs:
   - "Slack/communication Channels" → extract Slack channel names/URLs → resolve to channel IDs via Slack API
   - "Google Drive" → extract Drive folder URLs → extract folder IDs
   - "Code Links" → extract GitHub repo URLs → extract owner/repo slugs
   - "Design" → extract Figma file URLs → extract file keys
   - "Task Boards" → extract Jira/Linear URLs → extract project keys
   - "Meeting Notes" → extract meeting note locations (may be Notion pages, Drive folders, or Granola links)
4. Store the parsed config in the projects.config JSONB column
5. Create source entries for each discovered resource
```

### Connector Contracts

Each connector implements the same interface:

```typescript
interface Connector {
    // Discover sources from parsed Project Hub config
    discoverSources(config: ProjectConfig): Promise<Source[]>;

    // Fetch documents from a source, optionally since a timestamp
    fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]>;
}

interface RawDocument {
    sourceUrl: string;          // Deep link back to original
    content: string;            // Raw text content
    title: string;
    author?: string;
    date: Date;
    artifactType: string;       // meeting_note, prd, story, etc.
    sourceTool: string;         // notion, slack, github, etc.
}
```

### Connector Details

**Notion Connector**
- Uses Notion API (`@notionhq/client`)
- Fetches pages under the Project Hub and PHT entry
- Detects artifact type from page title patterns and parent structure (e.g., pages under "Meeting Notes" database = meeting_note)
- Incremental: filters by `last_edited_time > last_synced_at`

**Slack Connector**
- Uses Slack Web API (`@slack/web-api`)
- Fetches messages from project channels listed in the Hub
- Includes thread replies (each thread = one document)
- Filters out bot messages, emoji-only reactions, join/leave messages
- Incremental: uses `oldest` parameter with last sync timestamp

**GitHub Connector**
- Uses GitHub REST API (`@octokit/rest`)
- Fetches: README.md, CLAUDE.md, AGENTS.md, ADR files, PR descriptions + review comments
- Does NOT index source code (that's handled by agentic search in Claude Code)
- Incremental: uses `since` parameter on PR/issue endpoints

**Figma Connector**
- Uses Figma REST API
- Fetches: file metadata, page names, component names and descriptions, design token variables
- Lightweight — structured metadata only, not pixel data
- Full resync on each cycle (Figma doesn't have great incremental support)

**Google Drive Connector**
- Uses Google Drive API v3 (`google-api-python-client`) with GCP service account auth
- Discovers sources from Project Hub "Helpful Links" (folder URLs → recursive crawl, doc/slides URLs → individual fetch)
- Exports Google Docs and Slides to plain text via `files.export`
- Extracts text from PDFs (≤10 MB) via `pdfminer.six`
- Google Sheets are explicitly deferred (skipped)
- Incremental: filters by `modifiedTime > last_synced_at`
- Service account must be shared on target folders/docs to access them

**Atlassian (Jira) Connector**
- Uses Jira REST API
- Fetches: issues (summary, description, comments), sprint data, epic descriptions
- Scoped to the project board linked in the Hub
- Incremental: JQL `updated > last_synced_at`

### Chunking Strategy

```typescript
// Chunking rules by document type
const chunkingConfig = {
    meeting_note: {
        strategy: "by_heading",        // Split on H2/H3 headings (agenda items)
        targetSize: 500,               // tokens
        overlap: 50                    // token overlap between chunks
    },
    prd: {
        strategy: "by_section",        // Split on H1/H2 sections
        targetSize: 600,
        overlap: 50
    },
    story: {
        strategy: "whole_document",    // User stories are usually small enough to be one chunk
        targetSize: 800,
        overlap: 0
    },
    slack_thread: {
        strategy: "whole_thread",      // One thread = one chunk
        targetSize: 1000,
        overlap: 0
    },
    pr: {
        strategy: "by_section",        // PR description + each review comment as separate chunks
        targetSize: 500,
        overlap: 0
    },
    design_spec: {
        strategy: "by_component",      // Each component = one chunk
        targetSize: 400,
        overlap: 0
    },
    issue: {
        strategy: "whole_document",    // Jira issue = one chunk (summary + description + comments)
        targetSize: 800,
        overlap: 0
    },
    default: {
        strategy: "recursive_split",   // Fallback: recursive character splitting
        targetSize: 500,
        overlap: 50
    }
};
```

### Sync Scheduler

```
Cron schedule: run every 15 minutes during business hours, every hour otherwise
For each active project:
  1. Re-parse Project Hub (discover new/removed sources)
  2. For each source:
     a. Fetch documents modified since last sync
     b. Chunk and embed new/changed documents via Voyage.ai (input_type="document")
     c. Delete old vectors from Pinecone by source prefix, upsert new vectors
     d. Update source.last_synced_at and sync_status in Supabase
```

## Deployment

### Environment Variables

```bash
# .env.example

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...        # Service role key (server-side only, never exposed to clients)
SUPABASE_ANON_KEY=eyJ...                # Anon key (used for client auth flow)

# Connector credentials (org-level, managed by IT)
NOTION_API_TOKEN=secret_...
SLACK_BOT_TOKEN=xoxb-...
GITHUB_PAT=ghp_...
FIGMA_API_TOKEN=figd_...
ATLASSIAN_API_TOKEN=...
ATLASSIAN_EMAIL=service-account@verygood.ventures
ATLASSIAN_DOMAIN=verygoodventures.atlassian.net

# Google Drive
GOOGLE_SERVICE_ACCOUNT_JSON=...          # Base64-encoded service account JSON key, or path to key file

# Voyage.ai
VOYAGE_API_KEY=pa-...

# Pinecone
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=vgv-project-rag

# Service config
PORT=3000
SYNC_CRON="*/15 8-20 * * 1-5"          # Every 15min during business hours, weekdays
LOG_LEVEL=INFO
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src

EXPOSE 3000

CMD ["uv", "run", "python", "-m", "vgv_rag.main"]
```

### Docker Compose (for VPS deployment)

```yaml
version: "3.8"
services:
  rag-service:
    build: .
    ports:
      - "3002:3002"
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Google Cloud Run Deployment

```bash
# Build and push to Artifact Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/vgv-project-rag

# Deploy
gcloud run deploy vgv-project-rag \
  --image gcr.io/PROJECT_ID/vgv-project-rag \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "$(cat .env | tr '\n' ',')"
```

Note: Cloud Run scales to zero between requests. The first request after idle has a cold start (~2-5 seconds for the container). Embeddings are generated via Voyage.ai API (no local model to load). For the sync scheduler on Cloud Run, use Cloud Scheduler to trigger an HTTP endpoint on the service at the desired cron interval.

## Onboarding a Project

```bash
# CLI command to onboard a new project
npx ts-node scripts/seed-project.ts \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name"

# What this does:
# 1. Fetches the Project Hub page from Notion
# 2. Parses Helpful Links into connector configs
# 3. Creates a project record in Supabase
# 4. Creates source records for each discovered resource
# 5. Runs initial ingestion for all sources
# 6. Reports: sources discovered, documents indexed, any errors
```

## Onboarding a User

Users do not need to be manually onboarded. The flow:

1. User adds the MCP server URL to their Claude config:
   ```json
   {
     "mcpServers": {
       "vgv-project-rag": {
         "url": "https://rag.verygood.ventures/mcp"
       }
     }
   }
   ```
2. On first query, the service redirects to Supabase Auth (Google SSO)
3. User signs in with their `@verygood.ventures` Google account
4. JWT is issued and cached by the MCP client
5. Queries are automatically scoped to the user's projects via RLS

Project membership is derived from:
- The `project_members` table (populated by the seed script or manually)
- Future: auto-populate from Notion PHT team rosters or Slack channel membership

## Implementation Order

Build in this sequence. Each step produces a testable, working increment.

### Phase 1: Foundation
1. Initialize the repo: `package.json`, `tsconfig.json`, project structure
2. Set up Supabase: create project, run migrations (schema above), enable Google Auth
3. Build the MCP server skeleton: health endpoint, auth middleware, empty tool handlers
4. Build the embedding engine: `@xenova/transformers` wrapper that takes text and returns a 384-dim vector
5. Build the storage layer: Supabase client, insert chunks, vector similarity search
6. Wire up `search_project_context` tool with a hardcoded test project and manually inserted chunks
7. **Test:** Query the MCP server from Claude Code, verify auth flow and search results

### Phase 2: Ingestion
8. Build the Project Hub parser: fetch a Hub page, extract Helpful Links, resolve to connector configs
9. Build the Notion connector: fetch pages, detect artifact types, return RawDocuments
10. Build the chunker: implement strategies per document type
11. Build the sync scheduler: cron-based, calls connectors, chunks, embeds, stores
12. Build the `seed-project.ts` CLI script
13. **Test:** Onboard a real project, verify Notion pages are indexed and searchable

### Phase 3: Connectors
14. Slack connector
15. GitHub connector
16. Figma connector
17. Atlassian connector
18. **Test:** Full project index across all sources, verify cross-tool queries work

### Phase 4: Polish
19. `list_sources` tool implementation
20. `ingest_document` tool implementation
21. Sync error handling, retry logic, stale source detection
22. Dockerfile and deployment config (VPS or Cloud Run)
23. **Test:** Deploy to staging, onboard a project, verify end-to-end from Claude Code/Desktop/Cowork

## Key Design Decisions

- **Voyage.ai + Pinecone, not local embeddings + pgvector:** Cloud APIs eliminate the ~2GB torch dependency, dramatically shrink the Docker image, and provide higher-quality embeddings (voyage-4-lite, 1024-dim) with asymmetric query/document encoding. Pinecone's namespace isolation maps cleanly to project-per-namespace. Reranking via Voyage.ai rerank-2-lite improves result quality.
- **Supabase for relational data only:** Auth, projects, sources, and members stay in Supabase. Vector storage moved to Pinecone for better performance and simpler scaling.
- **Application-level membership checks:** With vectors in Pinecone (not Supabase), RLS no longer applies to search results. The search handler explicitly verifies project membership before querying Pinecone.
- **Project Hub as config, not a yaml file:** Eliminates admin UI, leverages the PgM's existing workflow, and ensures the RAG config stays in sync with the team's actual tool landscape.
- **Agentic search for code, RAG for project knowledge:** The service deliberately does NOT index source code. Claude Code's native grep/glob/file-read approach handles code better. This service handles the distributed, unstructured, multi-tool project knowledge that agentic search can't reach.