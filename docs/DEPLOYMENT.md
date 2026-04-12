# Production Deployment Guide

Step-by-step guide to deploying the VGV Project RAG Service to production.

For local development setup, see the [README](../README.md).

---

## Prerequisites

- [Docker](https://www.docker.com/) (for containerized deployment) or Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- A VGV Google Workspace account (for SSO)
- A domain or static IP for the deployment (for MCP URL + OAuth callback)

## 1. Create External Accounts

You need accounts with four services. All have free tiers sufficient for initial deployment.

### 1.1 Supabase (auth + relational database)

1. Go to [supabase.com](https://supabase.com) and create an account
2. Create a new project (choose a region close to your deployment)
3. Once the project is created, go to **Settings > API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **`anon` public key** → `SUPABASE_ANON_KEY`
   - **`service_role` secret key** → `SUPABASE_SERVICE_ROLE_KEY`

> The service role key has full access to your database. Never expose it to clients or commit it to version control.

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

Each connector is optional. The service activates only connectors whose credentials are present.

### Notion (required for auto-discovery)

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create an **Internal Integration** for the VGV workspace
3. Grant it access to the PHT teamspace (for auto-discovery) and any pages you want indexed
4. Copy the **Internal Integration Secret** → `NOTION_API_TOKEN`

> Without `NOTION_API_TOKEN`, auto-discovery is disabled and you must onboard projects manually with `seed_project.py`.

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

### GitHub (App — recommended)

A GitHub App provides org-level access to all repositories without personal tokens.

1. Go to **github.com/organizations/VGVentures/settings/apps**
2. Click **New GitHub App**
3. Configure:
   - **Name**: `vgv-project-rag`
   - **Homepage URL**: your deployment URL
   - **Webhook**: uncheck "Active" (not needed)
   - **Permissions**:
     - Repository: Contents (Read-only)
     - Repository: Pull requests (Read-only)
     - Repository: Issues (Read-only)
     - Repository: Metadata (Read-only)
   - **Where can this app be installed?**: Only on this account
4. Click **Create GitHub App**
5. Note the **App ID** → `GITHUB_APP_ID`
6. Generate a **Private Key** (.pem file) → `GITHUB_APP_PRIVATE_KEY` (paste the full PEM content including `-----BEGIN/END-----` headers)
7. Go to **Install App** tab, install on VGVentures with **All repositories**
8. Note the **Installation ID** from the URL → `GITHUB_APP_INSTALLATION_ID`

### GitHub (PAT — fallback)

If you can't set up a GitHub App, use a personal access token:

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

In the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new), paste and run each migration file in order:

| Migration | What it does |
|---|---|
| `001_initial_schema.sql` | Creates `projects`, `sources`, `project_members` tables |
| `002_remove_chunks.sql` | Removes unused pgvector chunks table |
| `003_add_programs.sql` | Adds `programs` table, program-project FKs, CHECK constraint, discovery RPC |

Files are in `src/vgv_rag/storage/migrations/`.

### Verify

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected: `programs`, `project_members`, `projects`, `sources`.

## 4. Configure the Environment

```bash
cp .env.example .env
```

Fill in all values. See the [README](../README.md#environment-variables) for the full variable reference.

**Minimum required for startup:**

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...
VOYAGE_API_KEY=pa-...
PINECONE_API_KEY=pcsk_...
```

**For auto-discovery (recommended):**

```bash
NOTION_API_TOKEN=secret_...
```

## 5. Deploy

### Option A: Docker Compose on a VPS

Recommended for Hetzner, DigitalOcean, Vultr, or any VPS with Docker installed.

```bash
# Clone the repo on your VPS
git clone https://github.com/VGVentures/vgv-project-brain.git
cd vgv-project-brain

# Create and fill in .env
cp .env.example .env
nano .env

# Build and start
docker-compose up --build -d
```

**Verify:**

```bash
curl http://localhost:3000/health
# {"status":"ok","service":"vgv-project-rag"}
```

**View logs:**

```bash
docker-compose logs -f rag-service
```

**Restart after config changes:**

```bash
docker-compose down && docker-compose up --build -d
```

**Expose via reverse proxy (nginx example):**

```nginx
server {
    listen 443 ssl;
    server_name rag.verygood.ventures;

    ssl_certificate     /etc/letsencrypt/live/rag.verygood.ventures/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rag.verygood.ventures/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;  # SSE connections are long-lived
    }
}
```

### Option B: Google Cloud Run

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
  --timeout 300 \
  --set-env-vars "SUPABASE_URL=...,SUPABASE_SERVICE_ROLE_KEY=...,SUPABASE_ANON_KEY=...,VOYAGE_API_KEY=...,PINECONE_API_KEY=...,PINECONE_INDEX_NAME=vgv-project-rag"
```

> **Secrets:** For sensitive values, use [Cloud Run secrets](https://cloud.google.com/run/docs/configuring/secrets) instead of `--set-env-vars`:
> ```bash
> gcloud run deploy vgv-project-rag \
>   --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-key:latest,VOYAGE_API_KEY=voyage-key:latest"
> ```

**Cloud Run + scheduler caveat:** Cloud Run scales to zero between requests. The built-in APScheduler won't run when there are no instances. Set up [Cloud Scheduler](https://console.cloud.google.com/cloudscheduler) to keep the scheduler running:

```bash
# Trigger sync every 15 minutes
gcloud scheduler jobs create http vgv-rag-sync \
  --schedule "*/15 * * * *" \
  --uri "https://vgv-project-rag-HASH-uc.a.run.app/health" \
  --http-method GET

# Trigger discovery hourly
gcloud scheduler jobs create http vgv-rag-discovery \
  --schedule "0 * * * *" \
  --uri "https://vgv-project-rag-HASH-uc.a.run.app/health" \
  --http-method GET
```

This keeps at least one instance warm during business hours. For true zero-cost idle, consider a VPS deployment instead.

### Option C: Run directly (no Docker)

```bash
uv sync --no-dev
uv run python -m vgv_rag.main
```

Use a process manager like `systemd` or `supervisord` to keep it running:

```ini
# /etc/systemd/system/vgv-rag.service
[Unit]
Description=VGV Project RAG Service
After=network.target

[Service]
Type=simple
User=vgv
WorkingDirectory=/opt/vgv-project-brain
EnvironmentFile=/opt/vgv-project-brain/.env
ExecStart=/usr/local/bin/uv run python -m vgv_rag.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable vgv-rag
sudo systemctl start vgv-rag
sudo journalctl -u vgv-rag -f  # view logs
```

## 6. Verify Deployment

### Startup checks

On startup, the service verifies:

1. **Supabase schema** — logs an error with the SQL Editor URL if tables are missing
2. **Pinecone index** — logs an error if the index is unreachable

Check logs for any errors after deploying.

### Health check

```bash
curl https://your-deployment-url/health
# {"status":"ok","service":"vgv-project-rag"}
```

### Connect a Claude interface

Add to your Claude MCP config:

```json
{
  "mcpServers": {
    "vgv-project-rag": {
      "url": "https://your-deployment-url/mcp"
    }
  }
}
```

On first query, users authenticate via Google SSO through Supabase Auth. The JWT is cached by the MCP client.

### Test a search

In Claude, try: *"Search for recent meeting notes about auth"*

If no results, check that:
1. At least one project has been onboarded (auto-discovery or `seed_project.py`)
2. Sources have synced (use `list_sources` tool to check status)
3. The user's email is in `project_members` for the relevant project

## 7. Auto-Onboarding

The service automatically discovers all programs and projects from the Notion PHT teamspace.

### Prerequisites
1. `NOTION_API_TOKEN` is set and the integration has access to the PHT teamspace
2. Program pages follow the template (contain a "Project Hubs" heading)
3. Project pages follow the template (contain a "Helpful Links" heading)

### How it works
- **On startup and hourly**: crawls Notion, discovers programs and projects, upserts records
- **Every 15 minutes during business hours**: syncs all discovered sources
- New programs/projects are picked up automatically on the next discovery cycle
- If a project is removed from a program page, its sources are marked `archived` (vectors preserved, not synced)

### Manual onboarding (optional)

For one-off imports or projects not in the PHT:

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/ProjectName-Hub-abc123" \
  --name "Project Name" \
  --member "alice@verygood.ventures" \
  --member "bob@verygood.ventures" \
  --program-url "https://www.notion.so/verygoodventures/ProgramPage-def456"  # optional
```

## 8. Upgrading an Existing Deployment

### Applying new migrations

When a new migration is added (e.g., `004_*.sql`):

1. Read the migration file to understand what it does
2. Run it in the [Supabase SQL Editor](https://supabase.com/dashboard/project/_/sql/new)
3. Restart the service

> Migrations are idempotent (`IF NOT EXISTS`, `IF EXISTS`) so re-running is safe.

### Deploying new code

**Docker Compose (VPS):**

```bash
cd /path/to/vgv-project-brain
git pull
docker-compose down && docker-compose up --build -d
```

**Cloud Run:**

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/vgv-project-rag
gcloud run deploy vgv-project-rag --image gcr.io/PROJECT_ID/vgv-project-rag
```

**Direct:**

```bash
git pull
uv sync --no-dev
sudo systemctl restart vgv-rag
```

## 9. Ongoing Operations

### Sync schedule

The service runs two scheduled jobs:
- **Discovery** (hourly + on startup): crawls Notion to discover new programs and projects
- **Source sync** (every 15 min during business hours, hourly otherwise): fetches new content from all discovered sources

### Monitoring

| What | How |
|---|---|
| Service health | `GET /health` |
| Source sync status | `list_sources` MCP tool, or query `sources` table in Supabase |
| Auth events | Supabase Dashboard > Authentication > Logs |
| Database size | Supabase Dashboard > Database > Reports |
| Vector count/latency | Pinecone Console > Index > Metrics |
| Application logs | `docker-compose logs -f` / `journalctl -u vgv-rag -f` / Cloud Run logs |

### Adding team members

Members are added per-project. Auto-discovery creates project records but does not assign members. Add members via:

**Seed script:**
```bash
uv run python scripts/seed_project.py \
  --hub-url "https://notion.so/existing-hub" \
  --name "Existing Project" \
  --member "newuser@verygood.ventures"
```

**SQL (Supabase SQL Editor or Dashboard):**
```sql
INSERT INTO project_members (project_id, user_email)
VALUES ('<project-uuid>', 'newuser@verygood.ventures');
```

### Adding new connectors

1. Add the connector's credentials to `.env`
2. Restart the service — connectors are initialized on startup
3. Sources from auto-discovery will begin syncing on the next cycle

### Rotating credentials

1. Update the credential in `.env`
2. Restart the service
3. Sources will re-authenticate on the next sync cycle

For GitHub App private keys, generate a new key in the GitHub App settings, update `GITHUB_APP_PRIVATE_KEY`, and restart.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Startup: "Database schema not found" | Migrations not run | Run SQL migrations in Supabase SQL Editor |
| Startup: "Pinecone index not found" | Index missing or wrong name | Create index in Pinecone console (1024 dims, cosine) |
| Search returns no results | No data indexed | Check `list_sources` — wait for sync or run `seed_project.py` |
| Search: "Not authorized" | User not in `project_members` | Add user email to the project |
| Search: "No projects found" | User has no project memberships | Add user to at least one project |
| Connector not activating | Missing env var | Check `.env` for the connector's credentials |
| Sync errors in `list_sources` | API rate limits or expired tokens | Check `sync_error` column, refresh the credential |
| Discovery finds no programs | Notion integration lacks access | Share the PHT teamspace with the integration |
| Discovery finds programs but no projects | Program pages missing "Project Hubs" heading | Verify page template |
| GitHub App: 401 errors | Wrong App ID, key, or installation ID | Regenerate private key, verify installation |
| Google Drive: 403 errors | Folder not shared with service account | Share folder with the SA email address |
| SSE connection drops | Reverse proxy timeout too short | Set `proxy_read_timeout 86400` in nginx |
