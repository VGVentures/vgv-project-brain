# feat: auto-onboard programs and projects from Notion PHT + GitHub App auth

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate manual project onboarding. The service automatically discovers all programs and projects by crawling the Notion PHT teamspace, indexes both program-level and project-level content, and syncs on a schedule. Additionally, replace GitHub PAT auth with a GitHub App for zero-config repo access.

**Brainstorm:** `docs/brainstorm/2026-04-09-auto-onboarding-github-app-brainstorm-doc.md`

**Architecture:**

```
Notion search() → identify program pages → parse program links
                                         → follow project hub links → parse project links
                                         → upsert programs, projects, sources
                                         → sync all sources (existing flow)
```

```mermaid
erDiagram
    programs ||--o{ projects : "has many"
    programs ||--o{ sources : "has program-level sources"
    projects ||--o{ sources : "has project-level sources"
    projects ||--o{ project_members : "has members"

    programs {
        uuid id PK
        text name
        text notion_page_url UK
        jsonb config
        timestamptz created_at
        timestamptz updated_at
    }
    projects {
        uuid id PK
        uuid program_id FK "nullable"
        text name
        text notion_hub_url UK
        jsonb config
        timestamptz created_at
        timestamptz updated_at
    }
    sources {
        uuid id PK
        uuid project_id FK "nullable — null for program-level"
        uuid program_id FK "nullable — set for program-level"
        text connector
        text source_url
        text source_id
        text sync_status
    }
    project_members {
        uuid id PK
        uuid project_id FK
        text user_email
    }
```

**Key design decisions from brainstorm + flow analysis:**
- **Programs are first-class entities** with their own table. Projects get `program_id` FK.
- **Program-level sources** attached directly to the program (via `program_id` on `sources` table) — not duplicated across child projects, not stored in a synthetic project.
- **Discovery runs hourly** (not every 15 min) to limit Notion API usage. Source sync stays at 15 min.
- **Program access model:** If a user is a member of any child project, they can search program-level content.
- **Stale project detection:** If a project disappears from a program page, mark its sources as `archived` — don't delete vectors.
- **GitHub App auth** with fallback to PAT. Token generated per sync cycle (tokens last 1 hour, cycles are 15 min). Token exchange uses `asyncio.to_thread` to avoid blocking the event loop.
- **Single GitHub installation** assumed (VGVentures org only). Multi-org support deferred.
- **`ProgramConfig` defined in `types.py`** alongside existing `ProjectConfig` and `Source` — follows codebase convention.
- **`Source` dataclass updated** to make `project_id` optional (`str | None`) for program-level sources. Pinecone namespace for program-level sources uses the `program_id`.
- **Sources unique constraint** updated: `UNIQUE(COALESCE(project_id, program_id), connector, source_id)` — handles nullable `project_id` for program-level sources.
- **Multi-namespace Pinecone search:** Query each namespace independently with proportional candidate budgets (`top_k * 4 / N` per namespace), merge all results, then rerank the combined set. On partial failure, return results from successful namespaces only.

**Plan split (from technical review):** This plan should be implemented as **2 independent PRs**:
- **PR 1: GitHub App auth** (Task 8 + Task 9 GitHub docs) — standalone, no dependencies
- **PR 2: Auto-onboarding** (Tasks 1–7, Task 9 onboarding docs, Task 10) — the larger feature

**Task ordering fix (from technical review):** Task 9 (update `upsert_project`/`upsert_source` signatures) moved to Task 3 (before discovery engine). Tasks renumbered accordingly.

**PR grouping:**
- **PR 1 (GitHub App):** Task 8, Task 9 (GitHub docs only)
- **PR 2 (Auto-onboarding):** Tasks 1–7, Task 9 (onboarding docs), Task 10

---

## Task 1: Database migration — programs table and schema changes

**Files:**
- Create: `src/vgv_rag/storage/migrations/003_add_programs.sql`

**Step 1: Write the migration**

```sql
-- 003_add_programs.sql
-- Add programs table and program-project relationship for auto-onboarding.

CREATE TABLE IF NOT EXISTS programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_page_url TEXT NOT NULL UNIQUE,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add program_id to projects (nullable — legacy projects may not have a program)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS program_id UUID REFERENCES programs(id) ON DELETE SET NULL;

-- Add program_id to sources (for program-level sources; mutually exclusive with project_id)
ALTER TABLE sources ADD COLUMN IF NOT EXISTS program_id UUID REFERENCES programs(id) ON DELETE CASCADE;

-- Drop old unique constraint (can't handle NULL project_id for program-level sources)
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_project_id_connector_source_id_key;

-- New unique constraint using COALESCE to handle nullable project_id/program_id
CREATE UNIQUE INDEX IF NOT EXISTS sources_owner_connector_source_id_idx
    ON sources (COALESCE(project_id, program_id), connector, source_id);

-- Index for looking up sources by program
CREATE INDEX IF NOT EXISTS sources_program_id_idx ON sources (program_id);
```

**Step 2: Commit**

```bash
git commit -m "feat: add programs table and program-project relationship migration"
```

---

## Task 2: Update supabase_queries.py with program operations

**Files:**
- Edit: `src/vgv_rag/storage/supabase_queries.py`
- Create: `tests/test_supabase_queries_programs.py`

**Step 1: Write failing tests**

Tests for:
- `upsert_program(name, notion_page_url, config)` → returns program ID
- `get_program_by_notion_url(url)` → returns program or None
- `list_all_programs()` → returns all programs
- `list_projects_for_program(program_id)` → returns projects under a program
- `list_programs_for_user(user_email)` → returns programs where user is a member of any child project
- `list_sources_for_program(program_id)` → returns sources attached to a program
- `get_project_by_id(project_id)` → returns project dict (needed by search to look up `program_id`)

**Step 2: Add functions to `supabase_queries.py`**

```python
async def upsert_program(name: str, notion_page_url: str, config: dict | None = None) -> str:
    # Upsert on notion_page_url, return program ID

async def get_program_by_notion_url(url: str) -> dict | None:
    # Lookup program by Notion page URL

async def list_all_programs() -> list[dict]:
    # Return all programs

async def list_projects_for_program(program_id: str) -> list[dict]:
    # Return projects with this program_id

async def list_programs_for_user(user_email: str) -> list[dict]:
    # Join project_members → projects → programs
    # Return distinct programs where user is a member of any child project

async def list_sources_for_program(program_id: str) -> list[dict]:
    # Return sources where program_id matches

async def get_project_by_id(project_id: str) -> dict | None:
    # Lookup project by ID (used by search to find parent program_id)
```

**Step 3: Run tests, commit**

```bash
git commit -m "feat: add program CRUD operations to supabase_queries"
```

---

## Task 3: Update `upsert_project` and `upsert_source` to accept `program_id`

**Files:**
- Edit: `src/vgv_rag/storage/supabase_queries.py`
- Edit: `src/vgv_rag/ingestion/connectors/types.py`
- Edit: `tests/test_supabase_queries.py`

**Must run before Task 5 (discovery engine) which calls these functions with `program_id`.**

**Step 1: Update `Source` dataclass in `types.py`**

Make `project_id` optional for program-level sources:

```python
@dataclass
class Source:
    id: str
    project_id: str | None      # None for program-level sources
    program_id: str | None = None  # Set for program-level sources
    connector: str
    source_url: str
    source_id: str
    last_synced_at: str | None = None
```

**Step 2: Update `upsert_project` signature**

```python
async def upsert_project(
    name: str, notion_hub_url: str, config: dict | None = None, program_id: str | None = None
) -> str:
    payload = {"name": name, "notion_hub_url": notion_hub_url, "config": config or {}}
    if program_id:
        payload["program_id"] = program_id
    # ... existing upsert logic
```

**Step 3: Update `upsert_source` to accept `program_id`**

For program-level sources, `project_id` is None and `program_id` is set.

```python
async def upsert_source(
    connector: str, source_url: str, source_id: str,
    project_id: str | None = None,
    program_id: str | None = None,
) -> str:
```

**Step 4: Update `sync_source` to use `program_id` as Pinecone namespace when `project_id` is None**

```python
namespace = source.project_id or source.program_id
```

**Step 5: Run tests, commit**

```bash
git commit -m "feat: update upsert_project, upsert_source, and Source for program_id support"
```

---

## Task 4: Create program page parser

**Files:**
- Edit: `src/vgv_rag/ingestion/connectors/types.py` (add `ProgramConfig`)
- Create: `src/vgv_rag/ingestion/program_parser.py`
- Create: `tests/test_program_parser.py`

**Step 1: Add `ProgramConfig` to `types.py`** (follows codebase convention — all dataclasses in `types.py`)

```python
@dataclass
class ProgramConfig:
    project_hub_urls: list[str]      # Links to project pages
    quick_links: list[str]           # Drive, SOW/MSA, account plans
    communication_channels: list[str] # Slack channels, etc.
```

**Step 2: Write failing tests**

Test that the parser:
- Identifies "Project Hubs" section and extracts project page links
- Identifies "Quick Links" section and extracts URLs (Drive, SOW, etc.)
- Identifies "Communication Channels" section and extracts Slack/channel URLs
- Returns a `ProgramConfig` dataclass with `project_hub_urls`, `quick_links`, `communication_channels`
- Handles pages that are NOT program pages (no "Project Hubs" heading) → returns None

**Step 3: Write `program_parser.py`**

Reuse `_extract_page_id` and URL extraction helpers from `project_hub_parser.py` — extract shared helpers into a common module or import directly.

```python
async def parse_program_page(page_url: str, notion_token: str) -> ProgramConfig | None:
    """Parse a Notion program page. Returns None if the page is not a program page."""
    # 1. Extract page ID from URL (reuse _extract_page_id from project_hub_parser)
    # 2. Fetch child blocks via Notion API
    # 3. Look for "Project Hubs" heading — if absent, return None (not a program page)
    # 4. Extract project hub links (Notion page URLs) from that section
    # 5. Look for "Quick Links" section, extract URLs (Drive, SOW, etc.)
    # 6. Look for "Communication Channels" section, extract URLs (Slack, etc.)
    # 7. Return ProgramConfig(project_hub_urls, quick_links, communication_channels)
```

**Step 4: Run tests, commit**

```bash
git commit -m "feat: add program page parser for Notion PHT"
```

---

## Task 5: Create discovery engine

**Files:**
- Create: `src/vgv_rag/ingestion/discovery.py`
- Create: `tests/test_discovery.py`

This is the core new component. It crawls Notion, identifies programs, discovers projects, and upserts everything to Supabase.

**Step 1: Write failing tests**

Test that discovery:
- Calls Notion `search()` with pagination (handles `has_more` + `next_cursor`)
- Filters pages through `parse_program_page` — skips non-program pages
- For each program: upserts program record, follows project hub links
- For each project: calls existing `parse_project_hub`, upserts project with `program_id`
- Creates source records for both program-level and project-level links
- Marks sources as `archived` if a project disappears from a program page
- Respects Notion rate limits (mock the semaphore)

**Step 2: Write `discovery.py`**

```python
import asyncio
import logging
from notion_client import AsyncClient

from vgv_rag.ingestion.program_parser import parse_program_page, ProgramConfig
from vgv_rag.ingestion.project_hub_parser import parse_project_hub, ProjectConfig
from vgv_rag.storage.supabase_queries import (
    upsert_program, upsert_project, upsert_source,
    list_all_programs, list_projects_for_program, list_sources_for_project,
)

log = logging.getLogger(__name__)

# Notion rate limit: 3 requests/second
_notion_semaphore = asyncio.Semaphore(3)


async def discover_all(notion_token: str) -> dict:
    """Crawl Notion, discover programs and projects, upsert records.
    
    Returns summary: {"programs_found": N, "projects_found": N, "sources_created": N}
    """
    client = AsyncClient(auth=notion_token)
    stats = {"programs_found": 0, "projects_found": 0, "sources_created": 0}

    # 1. Search all accessible pages (paginated)
    all_pages = await _search_all_pages(client)

    # 2. For each page, try to parse as a program page
    for page in all_pages:
        page_url = _page_to_url(page)
        program_config = await parse_program_page(page_url, notion_token)
        if program_config is None:
            continue  # Not a program page

        # 3. Upsert program
        program_name = _extract_title(page)
        program_id = await upsert_program(
            name=program_name,
            notion_page_url=page_url,
            config=_program_config_to_dict(program_config),
        )
        stats["programs_found"] += 1

        # 4. Create program-level sources (quick links, comms channels)
        stats["sources_created"] += await _create_program_sources(
            program_id, program_config
        )

        # 5. Discover projects from project hub links
        for hub_url in program_config.project_hub_urls:
            project_config = await parse_project_hub(hub_url, notion_token)
            if not project_config:
                continue

            project_name = _extract_project_name(hub_url)
            project_id = await upsert_project(
                name=project_name,
                notion_hub_url=hub_url,
                config=dataclasses.asdict(project_config),
                program_id=program_id,
            )
            stats["projects_found"] += 1

            # 6. Create project-level sources
            stats["sources_created"] += await _create_project_sources(
                project_id, project_config
            )

    # 7. Mark stale sources
    # Compare previously known projects (from DB) against discovered projects.
    # For each program, get existing projects from DB. If a project is in DB but
    # was NOT discovered in this cycle, mark its sources as sync_status="archived".
    # This handles projects removed from program pages without deleting vectors.
    await _mark_stale_sources(discovered_project_urls, stats)

    log.info("Discovery complete: %s", stats)
    return stats


async def _search_all_pages(client) -> list[dict]:
    """Paginated Notion search for all accessible pages."""
    pages = []
    cursor = None
    while True:
        async with _notion_semaphore:
            result = await client.search(
                filter={"property": "object", "value": "page"},
                start_cursor=cursor,
                page_size=100,
            )
        pages.extend(result["results"])
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]
    return pages


def _page_to_url(page: dict) -> str:
    """Construct a Notion URL from a page object's id."""

def _extract_title(page: dict) -> str:
    """Extract plain-text title from a Notion page object's properties."""

def _extract_project_name(hub_url: str) -> str:
    """Extract a human-readable project name from the Notion page URL slug."""

async def _create_program_sources(program_id: str, config: ProgramConfig) -> int:
    """Classify quick_links and communication_channels URLs, upsert as sources with program_id.
    Returns count of sources created."""

async def _create_project_sources(project_id: str, config: ProjectConfig) -> int:
    """Classify all URLs in ProjectConfig, upsert as sources with project_id.
    Reuses _classify_url from project_hub_parser. Returns count of sources created."""
```

**Note:** The scheduler's `run_sync` should skip sources with `sync_status="archived"` to avoid syncing removed projects.

**Step 3: Run tests, commit**

```bash
git commit -m "feat: add discovery engine for auto-onboarding from Notion"
```

---

## Task 6: Integrate discovery into scheduler and add program-level sync

**Files:**
- Edit: `src/vgv_rag/ingestion/scheduler.py`
- Edit: `tests/test_scheduler.py`

**Step 1: Update scheduler to run discovery before sync**

Add a separate hourly discovery job. The existing 15-minute sync job continues unchanged.

```python
from vgv_rag.ingestion.discovery import discover_all

def start_scheduler(get_connector, notion_token: str | None = None) -> AsyncIOScheduler:
    # ... existing code ...

    async def run_discovery():
        if not notion_token:
            return
        log.info("Discovery cycle starting...")
        stats = await discover_all(notion_token)
        log.info("Discovery complete: %s", stats)

    scheduler.add_job(run_discovery, "cron", minute=0)  # Hourly
    # Also run on startup (after a short delay to let connectors initialize)
    scheduler.add_job(run_discovery, "date", run_date=None)  # Immediate
```

**Step 2: Update `run_sync` to also sync program-level sources**

The existing sync loop iterates projects → sources. Add a second loop for programs → sources:

```python
async def run_sync():
    # ... existing project sync loop ...

    # Sync program-level sources
    programs = await list_all_programs()
    for program in programs:
        sources = await list_sources_for_program(program["id"])
        for source_dict in sources:
            connector = get_connector(source_dict["connector"])
            if not connector:
                continue
            source = Source(
                id=source_dict["id"],
                project_id=None,
                program_id=source_dict["program_id"],
                connector=source_dict["connector"],
                source_url=source_dict["source_url"],
                source_id=source_dict["source_id"],
                last_synced_at=source_dict.get("last_synced_at"),
            )
            await sync_source(source=source, connector=connector)
```

**Step 3: Update `main.py` to pass `notion_token` to scheduler**

```python
start_scheduler(registry.get, notion_token=settings.notion_api_token)
```

**Step 4: Update tests — mock `discover_all` and program sync in scheduler tests**

**Step 5: Run tests, commit**

```bash
git commit -m "feat: integrate discovery into scheduler with hourly cadence and program-level sync"
```

---

## Task 7: Update search tool for program-level content access

**Files:**
- Edit: `src/vgv_rag/server/tools/search.py`
- Edit: `tests/test_search_tool.py`

**Step 1: Write failing tests**

- Test: user who is a member of project SCO_001 (under program "Scooter's Coffee") can search program-level content
- Test: user who is NOT a member of any project under "Scooter's Coffee" cannot search program-level content
- Test: search with `project` filter works as before
- Test: search without `project` filter returns results from all user's projects AND their parent programs

**Step 2: Update search flow**

The key change: when querying Pinecone, include both the project namespace AND the parent program namespace (if any).

```python
# After resolving project_id and verifying membership:
namespaces_to_search = [project_id]

# Also search the parent program's namespace if user has access
project = await get_project_by_id(project_id)  # need to add this query
if project and project.get("program_id"):
    namespaces_to_search.append(project["program_id"])

# Query each namespace with proportional candidate budget
per_ns_candidates = max(top_k, (top_k * RERANK_CANDIDATE_MULTIPLIER) // len(namespaces_to_search))
all_candidates = []
for ns in namespaces_to_search:
    try:
        results = await query_vectors(namespace=ns, embedding=vector, top_k=per_ns_candidates, filters=filter_meta)
        all_candidates.extend(results)
    except Exception as exc:
        log.warning("Search failed for namespace %s: %s", ns, exc)

# Rerank the merged candidate set
results = await rerank(query, all_candidates, top_k=top_k)
```

If the user doesn't specify a project, search all their projects + all accessible programs (via `list_programs_for_user`).

**Step 3: Add `query_multiple_namespaces` helper to `pinecone_store.py`** (optional — can also just loop in search.py as shown above)

**Step 4: Run tests, commit**

```bash
git commit -m "feat: extend search to include program-level content for members"
```

---

## Task 8: Rewrite GitHub connector for App auth

**Files:**
- Edit: `src/vgv_rag/config/settings.py`
- Rewrite: `src/vgv_rag/ingestion/connectors/github.py`
- Edit: `tests/connectors/test_github.py`
- Edit: `.env.example`

**Step 1: Update settings**

Add to `settings.py`:

```python
# GitHub App (preferred — org-level, all repos)
github_app_id: Optional[str] = None
github_app_private_key: Optional[str] = None       # PEM-encoded private key or path to .pem file
github_app_installation_id: Optional[str] = None

# GitHub PAT (fallback)
github_pat: Optional[str] = None
```

Add to `.env.example`:

```bash
# GitHub (choose App OR PAT)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...
GITHUB_APP_INSTALLATION_ID=12345678
# OR
GITHUB_PAT=ghp_...
```

**Step 2: Write failing tests**

- Test: App auth generates JWT, exchanges for installation token
- Test: Installation token is used for API calls
- Test: Token refresh when expired
- Test: Fallback to PAT when App vars are absent
- Test: `discover_sources` and `fetch_documents` work with both auth methods

**Step 3: Rewrite `github.py`**

```python
import jwt  # PyJWT
import time
import httpx
from github import Github

class GitHubConnector:
    def __init__(
        self,
        app_id: str | None = None,
        private_key: str | None = None,
        installation_id: str | None = None,
        pat: str | None = None,
    ):
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._pat = pat
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _get_client(self) -> Github:
        """Get an authenticated GitHub client. Prefers App auth, falls back to PAT."""
        if self._app_id and self._private_key and self._installation_id:
            token = self._get_installation_token()
            return Github(token)
        elif self._pat:
            return Github(self._pat)
        else:
            raise RuntimeError("No GitHub credentials configured")

    def _get_installation_token(self) -> str:
        """Generate or reuse an installation access token."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        # Generate JWT (RS256, 10 min expiry)
        now = int(time.time())
        payload = {
            "iat": now - 60,       # Issued 60s ago (clock skew buffer)
            "exp": now + (10 * 60), # 10 minute expiry
            "iss": self._app_id,
        }
        encoded_jwt = jwt.encode(payload, self._private_key, algorithm="RS256")

        # Exchange JWT for installation token (synchronous — callers already wrap in to_thread)
        resp = httpx.post(
            f"https://api.github.com/app/installations/{self._installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        self._token_expires_at = time.time() + 3600  # Tokens last 1 hour
        return self._token

    # discover_sources and fetch_documents unchanged — just use self._get_client()
```

**Step 4: Update `main.py` connector registry**

```python
if settings.github_app_id and settings.github_app_private_key:
    connectors["github"] = GitHubConnector(
        app_id=settings.github_app_id,
        private_key=settings.github_app_private_key,
        installation_id=settings.github_app_installation_id,
    )
elif settings.github_pat:
    connectors["github"] = GitHubConnector(pat=settings.github_pat)
```

**Step 5: Add `PyJWT` dependency**

```bash
uv add PyJWT cryptography
```

(`cryptography` needed for RS256 signing)

**Step 6: Run tests, commit**

```bash
git commit -m "feat: add GitHub App auth with PAT fallback"
```

---

## Task 9: Update deployment docs

**Files:**
- Edit: `docs/DEPLOYMENT.md`
- Edit: `README.md`
- Edit: `CLAUDE.md`

**Step 1: Add GitHub App setup instructions to DEPLOYMENT.md**

Under the GitHub section, add:

```markdown
### GitHub (App — recommended)

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
6. Generate a **Private Key** (.pem file) → `GITHUB_APP_PRIVATE_KEY`
7. Go to **Install App** tab, install on VGVentures with **All repositories**
8. Note the **Installation ID** from the URL → `GITHUB_APP_INSTALLATION_ID`
```

**Step 2: Update auto-onboarding section**

Replace the manual `seed_project.py` section with:

```markdown
## Auto-Onboarding

The service automatically discovers all programs and projects from the Notion PHT teamspace.

### Prerequisites
1. Add the Notion integration to the PHT teamspace (gives access to all pages)
2. Ensure program pages follow the template (contain "Project Hubs" section)
3. Ensure project pages follow the template (contain "Helpful Links" section)

### How it works
- On startup and hourly: crawls Notion, discovers programs and projects
- Every 15 minutes: syncs all discovered sources
- New programs/projects are picked up automatically on the next discovery cycle

### Manual onboarding (optional)
The seed script is still available for one-off imports: ...
```

**Step 3: Update README and CLAUDE.md**

- Add programs to the architecture description
- Update project structure section
- Update env var tables

**Step 4: Commit**

```bash
git commit -m "docs: update deployment guide for auto-onboarding and GitHub App"
```

---

## Task 10: Cleanup and full test run

**Files:**
- Edit: `scripts/seed_project.py` (update to optionally accept `--program-url` for linking to a program)
- Edit: `src/vgv_rag/storage/migrate.py` (update `check_schema` to verify `programs` table exists)
- Run: `pytest -x` to verify all tests pass

**Step 1: Update `check_schema` to verify `programs` table**

**Step 2: Run full test suite**

```bash
pytest -x
```

**Step 3: Fix any remaining issues**

**Step 4: Commit**

```bash
git commit -m "chore: cleanup and verify full test suite"
```

---

## Acceptance Criteria

- [ ] `programs` table exists with `id`, `name`, `notion_page_url`, `config`
- [ ] `projects` table has `program_id` FK (nullable)
- [ ] `sources` table has `program_id` FK (nullable, for program-level sources)
- [ ] Discovery engine crawls Notion `search()` with pagination
- [ ] Program pages identified by "Project Hubs" heading presence
- [ ] Program-level links (Quick Links, Communication Channels) parsed and stored as sources
- [ ] Project pages parsed with existing `project_hub_parser`
- [ ] Discovery runs hourly on the scheduler (separate from 15-min source sync)
- [ ] Discovery also runs on startup
- [ ] Stale sources marked as `archived` when projects removed from program pages
- [ ] Notion API rate limited to 3 req/s via asyncio semaphore
- [ ] Search returns program-level content for users who are members of any child project
- [ ] GitHub connector authenticates via App (JWT → installation token) when App env vars present
- [ ] GitHub connector falls back to PAT when App env vars absent
- [ ] Installation token auto-refreshes before expiry
- [ ] `PyJWT` and `cryptography` added as dependencies
- [ ] Settings updated with `github_app_id`, `github_app_private_key`, `github_app_installation_id`
- [ ] `.env.example` updated with all new env vars
- [ ] Deployment guide updated with GitHub App setup and auto-onboarding docs
- [ ] README and CLAUDE.md updated
- [ ] All tests pass with mocked Notion, GitHub, Pinecone, and Voyage.ai SDKs
