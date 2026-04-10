---
date: 2026-04-09
topic: auto-onboarding-github-app
---

# Auto-Onboarding from Notion PHT + GitHub App Auth

## What We're Building

Two changes that eliminate manual configuration:

**1. Auto-onboarding from Notion teamspace.** Instead of running `seed_project.py` per project, the service automatically discovers all programs and projects by crawling the PHT teamspace in Notion. The Notion integration is added to the teamspace, giving it access to all pages. On startup and on the regular sync schedule, the service discovers programs, follows links to project hubs, parses their "Helpful Links" sections, and creates/syncs everything automatically. New programs or projects added to the teamspace are picked up on the next cycle.

**2. GitHub App auth (replaces PAT).** Instead of a personal access token scoped to specific repos, create a VGVentures org-level GitHub App with read-only access to all repositories. The service authenticates using the App's private key. New repos are automatically accessible without token rotation or config changes.

## Notion Teamspace Structure

```
PHT Teamspace (auto-discovered via Notion search API)
├── Program Page (e.g., "Scooter's Coffee Account Home")
│   ├── Quick Links (Google Drive, SOW/MSA, Account Plans)
│   ├── Communication Channels (program-level Slack, etc.)
│   └── Project Hubs section → links to project pages
│       ├── Project Page (e.g., "SCO_001 Scooter's Coffee")
│       │   └── Helpful Links (Slack, GitHub, Figma, Drive, Jira)
│       └── Project Page (e.g., "SCO_002 ...")
│           └── Helpful Links (...)
├── Another Program Page
│   └── ...
└── ...
```

- **Program pages** follow a template: contain "Project Hubs" section, quick links, comms channels
- **Project pages** follow a template: contain "Helpful Links" section (already parsed by `project_hub_parser.py`)
- Programs map to accounts/clients; projects map to SOWs/engagements
- Both program-level and project-level content should be indexed

## Why This Approach

### Auto-onboarding

Considered three approaches:
1. **Config list of program URLs** — simple but requires manual updates per program
2. **Crawl teamspace via Notion search API** — fully automatic, zero config (chosen)
3. **Notion database as registry** — PgM self-serve but requires creating a new database

Chose #2 because the user's goal is zero-touch: point the service at the teamspace and everything is discovered. The Notion `search()` API returns all pages the integration can access. We identify program pages by structural heuristics (contain a "Project Hubs" section), then follow links to discover projects.

### GitHub App

A GitHub App installed at the org level with "All repositories" access eliminates PAT rotation. The App authenticates with a private key + installation ID, generating short-lived tokens per request. New repos are automatically accessible.

## Key Decisions

- **Programs are first-class entities**: Add a `programs` table. Projects get a `program_id` foreign key. Program-level sources (Drive, comms channels) are indexed under the program. This preserves the real hierarchy instead of flattening everything.
- **Discovery via Notion search API**: Call `notion.search(filter={"object": "page"})` to get all accessible pages. Identify program pages by checking for "Project Hubs" heading in child blocks. Follow project links from that section.
- **Program page parser**: New parser (similar to `project_hub_parser.py`) that extracts program-level links — quick links (Drive, SOW), communication channels. Reuse the existing project hub parser for project pages.
- **Discovery runs on the sync schedule**: Every 15 minutes during business hours, the scheduler first discovers programs/projects (adds new ones, detects removed ones), then syncs all sources. No separate onboarding step.
- **`seed_project.py` becomes optional**: Kept for manual one-off imports but no longer required for normal operation. The scheduler handles everything.
- **Access stays per-project**: Users are scoped to individual projects. Program-level content access TBD — simplest model: if you're a member of any project under a program, you can search program-level content.
- **GitHub App replaces PAT**: New env vars `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_INSTALLATION_ID` replace `GITHUB_PAT`. The connector generates short-lived installation tokens via the GitHub App API. Old PAT auth kept as fallback if App vars are absent.
- **GitHub App setup docs**: Deployment guide updated with step-by-step App creation under VGVentures org, required permissions (Contents: read, Pull Requests: read, Issues: read), and installation.

## Data Model Changes

```sql
-- New: programs table
CREATE TABLE programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_page_url TEXT NOT NULL UNIQUE,
    config JSONB DEFAULT '{}'::jsonb,   -- Program-level parsed links
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Modified: projects gets program_id
ALTER TABLE projects ADD COLUMN program_id UUID REFERENCES programs(id) ON DELETE SET NULL;
```

## Discovery Flow

```
1. Notion search() → all accessible pages
2. For each page, fetch child blocks
3. If page contains "Project Hubs" heading → it's a program page
   a. Parse program-level links (Quick Links, Communication Channels)
   b. Upsert program record
   c. Extract project hub links from "Project Hubs" section
   d. For each project link:
      - Fetch the project page
      - Parse with existing project_hub_parser
      - Upsert project record (with program_id)
      - Create source records for discovered links
4. Sync all sources (existing scheduler flow)
```

## GitHub App Auth Flow

```
1. On connector init: load GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY
2. Generate JWT signed with private key (10 min expiry)
3. Exchange JWT for installation access token via GitHub API
4. Use installation token for all API calls (auto-refreshed on expiry)
5. Falls back to GITHUB_PAT if App vars not set
```

## Open Questions

- **Member auto-assignment**: Should we auto-populate `project_members` from Notion page permissions or Slack channel membership? Currently manual.
- **Program-level access model**: If a user is a member of project SCO_001, can they search program-level content for "Scooter's Coffee"? Proposed: yes, if member of any child project.
- **Stale project detection**: If a project is removed from the PHT, should we delete its vectors from Pinecone, or just stop syncing? Proposed: stop syncing, mark as "archived."
- **Rate limits**: Notion search + fetching blocks for every page on every cycle could hit rate limits. May need to cache the discovery results and only re-discover periodically (e.g., hourly) vs. syncing sources every 15 minutes.
