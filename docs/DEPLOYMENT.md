# Deployment Guide

Step-by-step guide to deploying the VGV Project RAG Service from scratch.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Docker](https://www.docker.com/) (for containerized deployment)
- A VGV Google Workspace account (for SSO)

## 1. Create External Accounts

You need accounts with four services. All have free tiers sufficient for initial deployment.

### 1.1 Supabase (auth + relational database)

1. Go to [supabase.com](https://supabase.com) and create an account
2. Create a new project (choose a region close to your deployment)
3. Once the project is created, go to **Settings > API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **`anon` public key** → `SUPABASE_ANON_KEY`
   - **`service_role` secret key** → `SUPABASE_SERVICE_ROLE_KEY`

> The service role key has full access to your database. Never expose it to clients.

### 1.2 Voyage.ai (embeddings + reranking)

1. Go to [dash.voyageai.com](https://dash.voyageai.com) and create an account
2. Navigate to **API Keys** and create a new key
3. Copy the key → `VOYAGE_API_KEY`

The service uses two Voyage.ai models:
- `voyage-4-lite` — embeddings (1024 dimensions)
- `rerank-2-lite` — search result reranking

### 1.3 Pinecone (vector database)

1. Go to [app.pinecone.io](https://app.pinecone.io) and create an account
2. Navigate to **API Keys** and copy your key → `PINECONE_API_KEY`
3. Create a new **serverless index**:
   - **Name**: `vgv-project-rag` (or your preferred name → `PINECONE_INDEX_NAME`)
   - **Dimensions**: `1024`
   - **Metric**: `cosine`
   - **Cloud/Region**: choose based on your deployment location

### 1.4 Supabase Auth (Google SSO)

1. In [Google Cloud Console](https://console.cloud.google.com):
   - Create a project (or use an existing one)
   - Go to **APIs & Services > Credentials**
   - Create an **OAuth 2.0 Client ID** (Web application)
   - Add the Supabase callback URL as an authorized redirect URI:
     `https://<your-project-ref>.supabase.co/auth/v1/callback`
   - Copy the **Client ID** and **Client Secret**
2. In the Supabase Dashboard:
   - Go to **Authentication > Providers > Google**
   - Enable the Google provider
   - Paste the Client ID and Client Secret
   - Under **Authentication > URL Configuration**, verify the redirect URL
3. Restrict signups to VGV emails:
   - In **Authentication > Settings**, set allowed email domains to `verygood.ventures`

## 2. Connector Credentials

Each connector is optional. The service activates only connectors whose credentials are present in the environment.

### Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create an **Internal Integration** for the VGV workspace
3. Grant it read access to the pages/databases you want to index
4. Copy the **Internal Integration Secret** → `NOTION_API_TOKEN`

### Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create a new app for the VGV workspace
3. Add the following **Bot Token Scopes**:
   - `channels:history` — read public channel messages
   - `channels:read` — list channels
   - `groups:history` — read private channel messages (if needed)
   - `groups:read` — list private channels
4. Install the app to the workspace
5. Copy the **Bot User OAuth Token** (`xoxb-...`) → `SLACK_BOT_TOKEN`
6. Invite the bot to each channel you want to index

### GitHub

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Create a **Fine-grained personal access token** (or classic token)
3. Grant read access to the repos you want to index:
   - Repository: Contents (read)
   - Pull Requests (read)
   - Issues (read)
4. Copy the token → `GITHUB_PAT`

### Figma

1. Go to [figma.com/developers/api](https://www.figma.com/developers/api#access-tokens)
2. Generate a **Personal Access Token**
3. Copy the token → `FIGMA_API_TOKEN`

### Google Drive

1. In [Google Cloud Console](https://console.cloud.google.com):
   - Go to **IAM & Admin > Service Accounts**
   - Create a service account (e.g., `vgv-rag-drive-reader`)
   - Create a JSON key for the service account and download it
2. Enable the **Google Drive API** for your project:
   - Go to **APIs & Services > Library**
   - Search for "Google Drive API" and enable it
3. Share target Drive folders/docs with the service account email
   (e.g., `vgv-rag-drive-reader@your-project.iam.gserviceaccount.com`)
4. Set the environment variable:
   - **Option A** (base64): `GOOGLE_SERVICE_ACCOUNT_JSON=$(base64 < service-account-key.json)`
   - **Option B** (file path): `GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account-key.json`

### Atlassian (Jira)

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create an API token
3. Set environment variables:
   - Token → `ATLASSIAN_API_TOKEN`
   - Service account email → `ATLASSIAN_EMAIL`
   - Your Atlassian domain (e.g., `verygoodventures.atlassian.net`) → `ATLASSIAN_DOMAIN`

## 3. Database Setup

### Run migrations

In the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new):

**For a fresh deployment**, run both migrations in order:

```sql
-- 1. Run 001_initial_schema.sql (creates projects, sources, project_members)
-- 2. Run 002_remove_chunks.sql  (removes the unused chunks table and pgvector)
```

Paste the contents of each file from `src/vgv_rag/storage/migrations/`.

**For an existing deployment** that previously used pgvector, run only `002_remove_chunks.sql`.

After running the migrations, verify the tables exist:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

You should see: `project_members`, `projects`, `sources`.

## 4. Configure the Environment

```bash
cp .env.example .env
```

Fill in all required values:

```bash
# Required — service won't start without these
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...
VOYAGE_API_KEY=pa-...
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=vgv-project-rag

# Optional — add connectors as needed
NOTION_API_TOKEN=secret_...
SLACK_BOT_TOKEN=xoxb-...
GITHUB_PAT=ghp_...
FIGMA_API_TOKEN=figd_...
GOOGLE_SERVICE_ACCOUNT_JSON=...
ATLASSIAN_API_TOKEN=...
ATLASSIAN_EMAIL=service-account@verygood.ventures
ATLASSIAN_DOMAIN=verygoodventures.atlassian.net
```

## 5. Deploy

### Option A: Docker Compose (VPS)

Recommended for Hetzner, DigitalOcean, Vultr, or any VPS with Docker installed.

```bash
docker-compose up --build -d
```

Verify it's running:

```bash
curl http://localhost:3000/health
# {"status":"ok","service":"vgv-project-rag"}
```

### Option B: Google Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/vgv-project-rag

# Deploy
gcloud run deploy vgv-project-rag \
  --image gcr.io/PROJECT_ID/vgv-project-rag \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "SUPABASE_URL=...,SUPABASE_SERVICE_ROLE_KEY=...,VOYAGE_API_KEY=...,PINECONE_API_KEY=..."
```

For the sync scheduler on Cloud Run, set up a [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler) job to hit the service periodically, since Cloud Run scales to zero between requests.

### Option C: Run directly

```bash
uv sync
uv run python -m vgv_rag.main
```

## 6. Verify Startup

On startup, the service checks:

1. **Supabase schema** — logs an error with the SQL Editor URL if tables are missing
2. **Pinecone index** — logs an error if the index is unreachable or doesn't exist

Check the logs for any errors:

```bash
# Docker
docker-compose logs -f rag-service

# Cloud Run
gcloud run services logs read vgv-project-rag

# Direct
# Logs print to stdout
```

## 7. Onboard a Project

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name" \
  --member "alice@verygood.ventures" \
  --member "bob@verygood.ventures"
```

This:
1. Parses the Notion Project Hub page
2. Discovers linked sources (Slack channels, GitHub repos, etc.)
3. Creates the project and source records in Supabase
4. Adds team members
5. Runs an initial Notion sync

## 8. Connect Claude Interfaces

Add the MCP server URL to your Claude configuration:

```json
{
  "mcpServers": {
    "vgv-project-rag": {
      "url": "https://your-deployment-url/mcp"
    }
  }
}
```

This works in Claude Code (`~/.claude.json`), Claude Desktop, and claude.ai.

On first query, users authenticate via Google SSO through Supabase Auth. The JWT is cached by the MCP client for subsequent requests.

## 9. Ongoing Operations

### Sync schedule

The service automatically syncs all project sources:
- Every 15 minutes during business hours (Mon-Fri, 8am-8pm)
- Every hour outside business hours

### Monitoring

- **Health check**: `GET /health`
- **Source status**: Use the `list_sources` MCP tool to check sync status and errors
- **Supabase Dashboard**: Monitor auth events, database size, and API usage
- **Pinecone Console**: Monitor vector count, query latency, and index size

### Adding new team members

Members are added per-project via the seed script (`--member` flag) or directly in Supabase:

```sql
INSERT INTO project_members (project_id, user_email)
VALUES ('<project-uuid>', 'newuser@verygood.ventures');
```

### Adding new connectors

1. Add the connector's credentials to `.env`
2. Restart the service — it auto-discovers new connectors on startup
3. Re-run the seed script or wait for the next sync cycle to pick up new sources

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Startup error: "Database schema not found" | Migrations not run | Run the SQL migrations in the Supabase SQL Editor |
| Startup error: "Pinecone index not found" | Index doesn't exist or wrong name | Create the index in Pinecone console (1024 dims, cosine) |
| Search returns no results | No data indexed yet | Run `seed_project.py` to onboard a project |
| "Not authorized" on search | User not in `project_members` | Add the user's email to the project |
| Connector not activating | Missing credentials | Check `.env` for the connector's token |
| Sync errors in `list_sources` | API rate limits or expired tokens | Check the `sync_error` field and refresh the token |
