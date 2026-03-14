# VGV Project RAG Service — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a centralized MCP server that indexes Notion, Slack, GitHub, Figma, and Jira artifacts into Supabase pgvector and serves semantic search to any Claude interface via Google SSO.

**Architecture:** TypeScript Node.js service exposing MCP tools over HTTP. A cron-based ingestion scheduler pulls documents from each connector, chunks and embeds them with `@xenova/transformers` (all-MiniLM-L6-v2), and upserts 384-dim vectors into Supabase pgvector. Row Level Security scopes queries per user via Supabase Auth (Google OAuth).

**Tech Stack:** TypeScript, `@modelcontextprotocol/sdk`, `@xenova/transformers`, `@supabase/supabase-js`, `@notionhq/client`, `@slack/web-api`, `@octokit/rest`, `node-cron`, Vitest (testing), Docker.

---

## Phase 1: Foundation

### Task 1: Initialize project structure and tooling

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/index.ts`
- Create: `src/config/env.ts`

**Step 1: Initialize npm and install dependencies**

```bash
npm init -y
npm install @modelcontextprotocol/sdk @supabase/supabase-js @xenova/transformers \
  @notionhq/client @slack/web-api @octokit/rest node-cron dotenv
npm install -D typescript @types/node @types/node-cron vitest tsx
```

**Step 2: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "declaration": true,
    "sourceMap": true
  },
  "include": ["src/**/*", "scripts/**/*"],
  "exclude": ["node_modules", "dist", "test"]
}
```

**Step 3: Write `package.json` scripts section**

Replace the scripts block:
```json
{
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "tsx watch src/index.ts",
    "test": "vitest run",
    "test:watch": "vitest",
    "setup-db": "tsx scripts/setup-supabase.ts",
    "seed": "tsx scripts/seed-project.ts"
  }
}
```

**Step 4: Write `.env.example`**

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...

# Connectors
NOTION_API_TOKEN=secret_...
SLACK_BOT_TOKEN=xoxb-...
GITHUB_PAT=ghp_...
FIGMA_API_TOKEN=figd_...
ATLASSIAN_API_TOKEN=...
ATLASSIAN_EMAIL=service-account@verygood.ventures
ATLASSIAN_DOMAIN=verygoodventures.atlassian.net

# Service
PORT=3000
SYNC_CRON="*/15 8-20 * * 1-5"
SYNC_CRON_OFF_HOURS="0 * * * *"
LOG_LEVEL=info
```

**Step 5: Write `.gitignore`**

```
node_modules/
dist/
.env
.cache/
*.js.map
```

**Step 6: Write minimal `src/index.ts` (just a health check stub)**

```typescript
import 'dotenv/config';

console.log('VGV Project RAG Service starting...');
```

**Step 7: Commit**

```bash
git add package.json tsconfig.json .env.example .gitignore src/index.ts
git commit -m "chore: initialize project structure and tooling"
```

---

### Task 2: Typed environment configuration

**Files:**
- Create: `src/config/env.ts`
- Create: `test/config/env.test.ts`

**Step 1: Write the failing test**

```typescript
// test/config/env.test.ts
import { describe, it, expect, beforeEach } from 'vitest';

describe('env config', () => {
  beforeEach(() => {
    process.env.SUPABASE_URL = 'https://test.supabase.co';
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'service-key';
    process.env.SUPABASE_ANON_KEY = 'anon-key';
    process.env.PORT = '3000';
  });

  it('reads SUPABASE_URL', async () => {
    const { env } = await import('../../src/config/env.js');
    expect(env.SUPABASE_URL).toBe('https://test.supabase.co');
  });

  it('throws on missing required var', async () => {
    delete process.env.SUPABASE_URL;
    await expect(import('../../src/config/env.js?bust=' + Date.now())).rejects.toThrow();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/config/env.test.ts
```
Expected: FAIL — module not found.

**Step 3: Write `src/config/env.ts`**

```typescript
function require_env(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`Missing required environment variable: ${key}`);
  return value;
}

export const env = {
  SUPABASE_URL: require_env('SUPABASE_URL'),
  SUPABASE_SERVICE_ROLE_KEY: require_env('SUPABASE_SERVICE_ROLE_KEY'),
  SUPABASE_ANON_KEY: require_env('SUPABASE_ANON_KEY'),
  NOTION_API_TOKEN: process.env.NOTION_API_TOKEN,
  SLACK_BOT_TOKEN: process.env.SLACK_BOT_TOKEN,
  GITHUB_PAT: process.env.GITHUB_PAT,
  FIGMA_API_TOKEN: process.env.FIGMA_API_TOKEN,
  ATLASSIAN_API_TOKEN: process.env.ATLASSIAN_API_TOKEN,
  ATLASSIAN_EMAIL: process.env.ATLASSIAN_EMAIL,
  ATLASSIAN_DOMAIN: process.env.ATLASSIAN_DOMAIN,
  PORT: parseInt(process.env.PORT ?? '3000', 10),
  SYNC_CRON: process.env.SYNC_CRON ?? '*/15 8-20 * * 1-5',
  SYNC_CRON_OFF_HOURS: process.env.SYNC_CRON_OFF_HOURS ?? '0 * * * *',
  LOG_LEVEL: process.env.LOG_LEVEL ?? 'info',
} as const;
```

**Step 4: Run test to verify it passes**

```bash
npx vitest run test/config/env.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/config/env.ts test/config/env.test.ts
git commit -m "feat: typed environment configuration with validation"
```

---

### Task 3: Database schema migration

**Files:**
- Create: `src/storage/migrations/001_initial_schema.sql`
- Create: `scripts/setup-supabase.ts`

**Step 1: Write the migration SQL**

```sql
-- src/storage/migrations/001_initial_schema.sql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Projects table (discovered from Notion Project Hubs)
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_hub_url TEXT NOT NULL UNIQUE,
    notion_pht_url TEXT,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Source tracking
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    connector TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_id TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ,
    sync_status TEXT DEFAULT 'pending',
    sync_error TEXT,
    UNIQUE(project_id, connector, source_id)
);

-- Chunks with vector embeddings
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast vector search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Indexes for filtered queries
CREATE INDEX IF NOT EXISTS chunks_project_artifact_idx
    ON chunks (project_id, (metadata->>'artifact_type'));
CREATE INDEX IF NOT EXISTS chunks_project_tool_idx
    ON chunks (project_id, (metadata->>'source_tool'));

-- Project team membership
CREATE TABLE IF NOT EXISTS project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_email TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    UNIQUE(project_id, user_email)
);

-- Row Level Security
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Users can read chunks from their projects"
    ON chunks FOR SELECT
    USING (
        project_id IN (
            SELECT project_id FROM project_members
            WHERE user_email = auth.jwt()->>'email'
        )
    );

-- Helper function: vector similarity search scoped to a project
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding VECTOR(384),
    match_project_id UUID,
    match_count INT DEFAULT 5,
    filter_metadata JSONB DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.content,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    WHERE
        c.project_id = match_project_id
        AND (filter_metadata IS NULL OR c.metadata @> filter_metadata)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

**Step 2: Write `scripts/setup-supabase.ts`**

```typescript
// scripts/setup-supabase.ts
import 'dotenv/config';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { createClient } from '@supabase/supabase-js';
import { env } from '../src/config/env.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const sql = readFileSync(
  join(__dirname, '../src/storage/migrations/001_initial_schema.sql'),
  'utf8'
);

const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

const { error } = await supabase.rpc('exec_sql', { sql });
if (error) {
  // Most likely the RPC doesn't exist — instruct manual run
  console.log('Run the following SQL in the Supabase SQL Editor:');
  console.log(sql);
} else {
  console.log('Migration applied successfully.');
}
```

**Step 3: Manual Supabase setup instructions**

> The migration SQL must be run manually in the Supabase Dashboard > SQL Editor until the `exec_sql` RPC exists. Copy `src/storage/migrations/001_initial_schema.sql` and paste it in the editor.
>
> Also enable Google Auth in Supabase Dashboard > Authentication > Providers > Google. Restrict to `@verygood.ventures` domain.

**Step 4: Commit**

```bash
git add src/storage/migrations/001_initial_schema.sql scripts/setup-supabase.ts
git commit -m "feat: database schema with pgvector, RLS, and match_chunks function"
```

---

### Task 4: Supabase storage layer

**Files:**
- Create: `src/storage/supabase.ts`
- Create: `src/storage/queries.ts`
- Create: `test/storage/queries.test.ts`

**Step 1: Write the failing tests**

```typescript
// test/storage/queries.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the supabase module so tests don't hit the network
vi.mock('../../src/storage/supabase.js', () => ({
  supabase: {
    from: vi.fn(),
    rpc: vi.fn(),
  },
}));

import { supabase } from '../../src/storage/supabase.js';
import { insertChunks, searchChunks, upsertProject, upsertSource } from '../../src/storage/queries.js';

describe('insertChunks', () => {
  it('inserts chunk rows into supabase', async () => {
    const mockInsert = vi.fn().mockResolvedValue({ error: null });
    (supabase.from as any).mockReturnValue({ insert: mockInsert });

    await insertChunks([{
      project_id: 'proj-1',
      source_id: 'src-1',
      content: 'hello world',
      embedding: new Array(384).fill(0),
      metadata: { artifact_type: 'prd', source_tool: 'notion' },
    }]);

    expect(supabase.from).toHaveBeenCalledWith('chunks');
    expect(mockInsert).toHaveBeenCalled();
  });
});

describe('searchChunks', () => {
  it('calls match_chunks rpc with correct params', async () => {
    (supabase.rpc as any).mockResolvedValue({
      data: [{ id: '1', content: 'test', metadata: {}, similarity: 0.9 }],
      error: null,
    });

    const results = await searchChunks({
      embedding: new Array(384).fill(0),
      project_id: 'proj-1',
      top_k: 5,
    });

    expect(supabase.rpc).toHaveBeenCalledWith('match_chunks', expect.objectContaining({
      query_embedding: expect.any(Array),
      match_project_id: 'proj-1',
      match_count: 5,
    }));
    expect(results).toHaveLength(1);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/storage/queries.test.ts
```
Expected: FAIL — module not found.

**Step 3: Write `src/storage/supabase.ts`**

```typescript
// src/storage/supabase.ts
import { createClient } from '@supabase/supabase-js';
import { env } from '../config/env.js';

export const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

// Create a user-scoped client from a JWT (respects RLS)
export function createUserClient(jwt: string) {
  return createClient(env.SUPABASE_URL, env.SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: `Bearer ${jwt}` } },
  });
}
```

**Step 4: Write `src/storage/queries.ts`**

```typescript
// src/storage/queries.ts
import { supabase } from './supabase.js';

export interface ChunkRow {
  project_id: string;
  source_id: string;
  content: string;
  embedding: number[];
  metadata: Record<string, unknown>;
}

export interface SearchParams {
  embedding: number[];
  project_id: string;
  top_k?: number;
  filter_metadata?: Record<string, unknown>;
}

export interface SearchResult {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  similarity: number;
}

export async function insertChunks(chunks: ChunkRow[]): Promise<void> {
  const { error } = await supabase.from('chunks').insert(chunks);
  if (error) throw new Error(`insertChunks failed: ${error.message}`);
}

export async function deleteChunksBySource(source_id: string): Promise<void> {
  const { error } = await supabase.from('chunks').delete().eq('source_id', source_id);
  if (error) throw new Error(`deleteChunksBySource failed: ${error.message}`);
}

export async function searchChunks(params: SearchParams): Promise<SearchResult[]> {
  const { data, error } = await supabase.rpc('match_chunks', {
    query_embedding: params.embedding,
    match_project_id: params.project_id,
    match_count: params.top_k ?? 5,
    filter_metadata: params.filter_metadata ?? null,
  });
  if (error) throw new Error(`searchChunks failed: ${error.message}`);
  return data as SearchResult[];
}

export async function upsertProject(project: {
  name: string;
  notion_hub_url: string;
  notion_pht_url?: string;
  config?: Record<string, unknown>;
}): Promise<string> {
  const { data, error } = await supabase
    .from('projects')
    .upsert(project, { onConflict: 'notion_hub_url' })
    .select('id')
    .single();
  if (error) throw new Error(`upsertProject failed: ${error.message}`);
  return data.id;
}

export async function upsertSource(source: {
  project_id: string;
  connector: string;
  source_url: string;
  source_id: string;
}): Promise<string> {
  const { data, error } = await supabase
    .from('sources')
    .upsert(source, { onConflict: 'project_id,connector,source_id' })
    .select('id')
    .single();
  if (error) throw new Error(`upsertSource failed: ${error.message}`);
  return data.id;
}

export async function updateSourceSyncStatus(
  source_id: string,
  status: 'syncing' | 'success' | 'error',
  error_msg?: string
): Promise<void> {
  const { error } = await supabase
    .from('sources')
    .update({
      sync_status: status,
      sync_error: error_msg ?? null,
      last_synced_at: status === 'success' ? new Date().toISOString() : undefined,
    })
    .eq('id', source_id);
  if (error) throw new Error(`updateSourceSyncStatus failed: ${error.message}`);
}

export async function listSourcesForProject(project_id: string) {
  const { data, error } = await supabase
    .from('sources')
    .select('*')
    .eq('project_id', project_id);
  if (error) throw new Error(`listSourcesForProject failed: ${error.message}`);
  return data;
}

export async function getProjectByName(name: string) {
  const { data, error } = await supabase
    .from('projects')
    .select('*')
    .ilike('name', name)
    .single();
  if (error) return null;
  return data;
}

export async function listProjectsForUser(user_email: string) {
  const { data, error } = await supabase
    .from('project_members')
    .select('project_id, projects(*)')
    .eq('user_email', user_email);
  if (error) throw new Error(`listProjectsForUser failed: ${error.message}`);
  return data?.map((row: any) => row.projects) ?? [];
}
```

**Step 5: Run tests to verify they pass**

```bash
npx vitest run test/storage/queries.test.ts
```
Expected: PASS.

**Step 6: Commit**

```bash
git add src/storage/supabase.ts src/storage/queries.ts test/storage/queries.test.ts
git commit -m "feat: storage layer with Supabase client, insert, search, and project queries"
```

---

### Task 5: Embedding engine

**Files:**
- Create: `src/processing/embedder.ts`
- Create: `test/processing/embedder.test.ts`

**Step 1: Write the failing test**

```typescript
// test/processing/embedder.test.ts
import { describe, it, expect } from 'vitest';

describe('embedder', () => {
  it('returns a 384-dimensional vector for any text', async () => {
    const { embed } = await import('../../src/processing/embedder.js');
    const vector = await embed('hello world');
    expect(vector).toHaveLength(384);
    expect(vector.every(v => typeof v === 'number')).toBe(true);
  }, 60_000); // model download takes time on first run

  it('returns different vectors for different text', async () => {
    const { embed } = await import('../../src/processing/embedder.js');
    const v1 = await embed('project planning');
    const v2 = await embed('database schema');
    expect(v1).not.toEqual(v2);
  }, 60_000);
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/processing/embedder.test.ts
```
Expected: FAIL — module not found.

**Step 3: Write `src/processing/embedder.ts`**

```typescript
// src/processing/embedder.ts
import { pipeline, env as transformersEnv } from '@xenova/transformers';
import { join } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

// Cache model in project directory
const __dirname = dirname(fileURLToPath(import.meta.url));
transformersEnv.cacheDir = process.env.TRANSFORMERS_CACHE ??
  join(__dirname, '../../.cache/transformers');

// Singleton pipeline — initialized once, reused for all embeddings
let pipelineInstance: Awaited<ReturnType<typeof pipeline>> | null = null;

async function getPipeline() {
  if (!pipelineInstance) {
    pipelineInstance = await pipeline(
      'feature-extraction',
      'Xenova/all-MiniLM-L6-v2'
    );
  }
  return pipelineInstance;
}

export async function embed(text: string): Promise<number[]> {
  const pipe = await getPipeline();
  const output = await pipe(text, { pooling: 'mean', normalize: true });
  return Array.from(output.data) as number[];
}

export async function embedBatch(texts: string[]): Promise<number[][]> {
  return Promise.all(texts.map(embed));
}
```

**Step 4: Run tests (will download model ~80MB on first run)**

```bash
npx vitest run test/processing/embedder.test.ts
```
Expected: PASS (may take 30–60s on first run while model downloads).

**Step 5: Commit**

```bash
git add src/processing/embedder.ts test/processing/embedder.test.ts .gitignore
# Ensure .cache/ is in .gitignore
git commit -m "feat: embedding engine using @xenova/transformers all-MiniLM-L6-v2"
```

---

### Task 6: Chunking engine

**Files:**
- Create: `src/processing/chunker.ts`
- Create: `test/processing/chunker.test.ts`

**Step 1: Write the failing tests**

```typescript
// test/processing/chunker.test.ts
import { describe, it, expect } from 'vitest';
import { chunk } from '../../src/processing/chunker.js';

const MEETING_NOTE = `
# Team Sync

## Action Items
Alice will review the PR by Friday.
Bob will update the design doc.

## Decisions
We decided to use Supabase for auth.
The team agreed to skip the staging environment.

## Next Steps
Schedule a follow-up for next week.
`.trim();

describe('chunk', () => {
  it('splits meeting_note by heading', () => {
    const chunks = chunk(MEETING_NOTE, 'meeting_note');
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks[0]).toContain('Action Items');
  });

  it('returns whole_document for slack_thread', () => {
    const text = 'Short slack thread message.';
    const chunks = chunk(text, 'slack_thread');
    expect(chunks).toHaveLength(1);
    expect(chunks[0]).toBe(text);
  });

  it('returns whole_document for story', () => {
    const text = 'As a user I want to search project knowledge.';
    const chunks = chunk(text, 'story');
    expect(chunks).toHaveLength(1);
  });

  it('uses recursive_split as fallback', () => {
    const longText = 'word '.repeat(2000);
    const chunks = chunk(longText, 'unknown_type');
    expect(chunks.length).toBeGreaterThan(1);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/processing/chunker.test.ts
```
Expected: FAIL.

**Step 3: Write `src/processing/chunker.ts`**

```typescript
// src/processing/chunker.ts

// Approximate tokens: 1 token ≈ 4 chars (rough, good enough for chunking)
const CHARS_PER_TOKEN = 4;

type ArtifactType =
  | 'meeting_note' | 'prd' | 'story' | 'slack_thread'
  | 'pr' | 'design_spec' | 'issue' | string;

interface ChunkConfig {
  strategy: 'by_heading' | 'by_section' | 'whole_document' | 'whole_thread' | 'by_component' | 'recursive_split';
  targetSize: number;  // tokens
  overlap: number;     // tokens
}

const CHUNKING_CONFIG: Record<string, ChunkConfig> = {
  meeting_note: { strategy: 'by_heading', targetSize: 500, overlap: 50 },
  prd:          { strategy: 'by_section', targetSize: 600, overlap: 50 },
  story:        { strategy: 'whole_document', targetSize: 800, overlap: 0 },
  slack_thread: { strategy: 'whole_thread', targetSize: 1000, overlap: 0 },
  pr:           { strategy: 'by_section', targetSize: 500, overlap: 0 },
  design_spec:  { strategy: 'by_component', targetSize: 400, overlap: 0 },
  issue:        { strategy: 'whole_document', targetSize: 800, overlap: 0 },
  default:      { strategy: 'recursive_split', targetSize: 500, overlap: 50 },
};

export function chunk(text: string, artifactType: ArtifactType): string[] {
  const config = CHUNKING_CONFIG[artifactType] ?? CHUNKING_CONFIG.default;

  switch (config.strategy) {
    case 'whole_document':
    case 'whole_thread':
      return [text.trim()];

    case 'by_heading':
      return splitByHeading(text, /^#{2,3}\s/m, config);

    case 'by_section':
      return splitByHeading(text, /^#{1,2}\s/m, config);

    case 'by_component':
      return splitByHeading(text, /^#{1,3}\s/m, config);

    case 'recursive_split':
    default:
      return recursiveSplit(text, config.targetSize * CHARS_PER_TOKEN, config.overlap * CHARS_PER_TOKEN);
  }
}

function splitByHeading(text: string, headingRegex: RegExp, config: ChunkConfig): string[] {
  const lines = text.split('\n');
  const sections: string[] = [];
  let current: string[] = [];

  for (const line of lines) {
    if (headingRegex.test(line) && current.length > 0) {
      sections.push(current.join('\n').trim());
      current = [];
    }
    current.push(line);
  }
  if (current.length > 0) sections.push(current.join('\n').trim());

  // If any section is too large, recursively split it
  return sections.flatMap(section => {
    const targetChars = config.targetSize * CHARS_PER_TOKEN;
    if (section.length <= targetChars) return [section];
    return recursiveSplit(section, targetChars, config.overlap * CHARS_PER_TOKEN);
  }).filter(s => s.length > 0);
}

function recursiveSplit(text: string, targetChars: number, overlapChars: number): string[] {
  if (text.length <= targetChars) return [text];

  const separators = ['\n\n', '\n', '. ', ' ', ''];
  for (const sep of separators) {
    const parts = sep ? text.split(sep) : [...text];
    if (parts.length <= 1) continue;

    const chunks: string[] = [];
    let current = '';

    for (const part of parts) {
      const candidate = current ? current + sep + part : part;
      if (candidate.length > targetChars && current.length > 0) {
        chunks.push(current);
        current = overlapChars > 0
          ? current.slice(-overlapChars) + sep + part
          : part;
      } else {
        current = candidate;
      }
    }
    if (current) chunks.push(current);
    return chunks.filter(c => c.trim().length > 0);
  }
  return [text];
}
```

**Step 4: Run tests**

```bash
npx vitest run test/processing/chunker.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/processing/chunker.ts test/processing/chunker.test.ts
git commit -m "feat: semantic chunking engine with per-artifact-type strategies"
```

---

### Task 7: MCP server — skeleton with health endpoint

**Files:**
- Create: `src/server/mcp-server.ts`
- Modify: `src/index.ts`

**Step 1: Write the MCP server skeleton**

```typescript
// src/server/mcp-server.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import http from 'http';
import { env } from '../config/env.js';

export function createMcpServer(): McpServer {
  const server = new McpServer({
    name: 'vgv-project-rag',
    version: '1.0.0',
  });

  // Register tools (handlers are filled in later tasks)
  server.tool('search_project_context', 'Search project knowledge across Notion, Slack, GitHub, Figma, and Jira.', {
    query: { type: 'string' as const, description: 'Natural language search query' },
  }, async (args) => {
    return { content: [{ type: 'text', text: 'Not yet implemented' }] };
  });

  server.tool('list_sources', 'Show indexed sources for a project.', {}, async () => {
    return { content: [{ type: 'text', text: 'Not yet implemented' }] };
  });

  server.tool('ingest_document', 'Manually add a document to the project index.', {
    project: { type: 'string' as const },
  }, async (args) => {
    return { content: [{ type: 'text', text: 'Not yet implemented' }] };
  });

  return server;
}

export async function startHttpServer(server: McpServer): Promise<void> {
  const httpServer = http.createServer(async (req, res) => {
    // Health check
    if (req.url === '/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok', service: 'vgv-project-rag' }));
      return;
    }

    // MCP endpoint
    if (req.url === '/mcp') {
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
      await server.connect(transport);
      await transport.handleRequest(req, res, await readBody(req));
      return;
    }

    res.writeHead(404);
    res.end('Not found');
  });

  httpServer.listen(env.PORT, () => {
    console.log(`VGV Project RAG Service listening on port ${env.PORT}`);
    console.log(`MCP endpoint: http://localhost:${env.PORT}/mcp`);
  });
}

async function readBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try { resolve(JSON.parse(body || '{}')); }
      catch { resolve({}); }
    });
    req.on('error', reject);
  });
}
```

**Step 2: Update `src/index.ts`**

```typescript
// src/index.ts
import 'dotenv/config';
import { createMcpServer, startHttpServer } from './server/mcp-server.js';

const server = createMcpServer();
await startHttpServer(server);
```

**Step 3: Manual smoke test**

```bash
npm run dev &
curl http://localhost:3000/health
# Expected: {"status":"ok","service":"vgv-project-rag"}
kill %1
```

**Step 4: Commit**

```bash
git add src/server/mcp-server.ts src/index.ts
git commit -m "feat: MCP server skeleton with health endpoint and stub tool handlers"
```

---

### Task 8: Auth middleware (Supabase JWT validation)

**Files:**
- Create: `src/server/auth.ts`
- Create: `test/server/auth.test.ts`

**Step 1: Write failing tests**

```typescript
// test/server/auth.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/storage/supabase.js', () => ({
  supabase: {
    auth: {
      getUser: vi.fn(),
    },
  },
}));

import { supabase } from '../../src/storage/supabase.js';
import { validateJwt } from '../../src/server/auth.js';

describe('validateJwt', () => {
  it('returns user email when JWT is valid', async () => {
    (supabase.auth.getUser as any).mockResolvedValue({
      data: { user: { email: 'alice@verygood.ventures' } },
      error: null,
    });

    const email = await validateJwt('valid-token');
    expect(email).toBe('alice@verygood.ventures');
  });

  it('throws when JWT is invalid', async () => {
    (supabase.auth.getUser as any).mockResolvedValue({
      data: { user: null },
      error: { message: 'Invalid JWT' },
    });

    await expect(validateJwt('bad-token')).rejects.toThrow('Unauthorized');
  });

  it('throws when user has non-VGV email', async () => {
    (supabase.auth.getUser as any).mockResolvedValue({
      data: { user: { email: 'hacker@evil.com' } },
      error: null,
    });

    await expect(validateJwt('valid-token')).rejects.toThrow('Unauthorized');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/server/auth.test.ts
```
Expected: FAIL.

**Step 3: Write `src/server/auth.ts`**

```typescript
// src/server/auth.ts
import { supabase } from '../storage/supabase.js';

const ALLOWED_DOMAIN = '@verygood.ventures';

export async function validateJwt(token: string): Promise<string> {
  const { data, error } = await supabase.auth.getUser(token);

  if (error || !data.user?.email) {
    throw new Error('Unauthorized: invalid token');
  }

  if (!data.user.email.endsWith(ALLOWED_DOMAIN)) {
    throw new Error('Unauthorized: not a VGV account');
  }

  return data.user.email;
}

export function extractBearerToken(authHeader: string | undefined): string | null {
  if (!authHeader?.startsWith('Bearer ')) return null;
  return authHeader.slice('Bearer '.length);
}
```

**Step 4: Run tests**

```bash
npx vitest run test/server/auth.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/auth.ts test/server/auth.test.ts
git commit -m "feat: JWT validation middleware with VGV domain enforcement"
```

---

### Task 9: `search_project_context` tool — fully wired

**Files:**
- Modify: `src/server/mcp-server.ts`
- Create: `test/server/search-tool.test.ts`

**Step 1: Write failing test**

```typescript
// test/server/search-tool.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/storage/queries.js', () => ({
  searchChunks: vi.fn().mockResolvedValue([
    { id: '1', content: 'PRD section about auth', metadata: { source_tool: 'notion', artifact_type: 'prd', source_url: 'https://notion.so/123' }, similarity: 0.92 },
  ]),
  listProjectsForUser: vi.fn().mockResolvedValue([{ id: 'proj-1', name: 'TestProject' }]),
  getProjectByName: vi.fn().mockResolvedValue({ id: 'proj-1', name: 'TestProject' }),
}));

vi.mock('../../src/processing/embedder.js', () => ({
  embed: vi.fn().mockResolvedValue(new Array(384).fill(0.1)),
}));

import { handleSearchProjectContext } from '../../src/server/tools/search.js';

describe('handleSearchProjectContext', () => {
  it('returns formatted chunks for a valid query', async () => {
    const result = await handleSearchProjectContext({
      query: 'how does auth work',
      user_email: 'alice@verygood.ventures',
    });

    expect(result.content[0].text).toContain('PRD section about auth');
    expect(result.content[0].text).toContain('notion.so/123');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/server/search-tool.test.ts
```
Expected: FAIL.

**Step 3: Extract tool handler into `src/server/tools/search.ts`**

```typescript
// src/server/tools/search.ts
import { embed } from '../../processing/embedder.js';
import { searchChunks, listProjectsForUser, getProjectByName } from '../../storage/queries.js';

export interface SearchArgs {
  query: string;
  user_email: string;
  project?: string;
  filters?: {
    artifact_type?: string;
    source_tool?: string;
    phase?: string;
    after?: string;
    before?: string;
  };
  top_k?: number;
}

export async function handleSearchProjectContext(args: SearchArgs) {
  const { query, user_email, project, filters, top_k = 5 } = args;

  // Resolve project
  let projectId: string;
  if (project) {
    const proj = await getProjectByName(project);
    if (!proj) throw new Error(`Project not found: ${project}`);
    projectId = proj.id;
  } else {
    const projects = await listProjectsForUser(user_email);
    if (projects.length === 0) throw new Error('No projects found for user');
    projectId = projects[0].id; // Default to first project
  }

  // Build metadata filter
  const filter_metadata: Record<string, unknown> = {};
  if (filters?.artifact_type) filter_metadata.artifact_type = filters.artifact_type;
  if (filters?.source_tool) filter_metadata.source_tool = filters.source_tool;
  if (filters?.phase) filter_metadata.phase = filters.phase;

  // Embed query and search
  const embedding = await embed(query);
  const chunks = await searchChunks({
    embedding,
    project_id: projectId,
    top_k: Math.min(top_k, 20),
    filter_metadata: Object.keys(filter_metadata).length > 0 ? filter_metadata : undefined,
  });

  if (chunks.length === 0) {
    return { content: [{ type: 'text' as const, text: 'No relevant results found.' }] };
  }

  const formatted = chunks.map((c, i) => {
    const meta = c.metadata as Record<string, string>;
    return [
      `--- Result ${i + 1} (similarity: ${(c.similarity * 100).toFixed(0)}%) ---`,
      `Source: ${meta.source_tool ?? 'unknown'} | Type: ${meta.artifact_type ?? 'unknown'}`,
      meta.source_url ? `URL: ${meta.source_url}` : null,
      meta.author ? `Author: ${meta.author}` : null,
      meta.date ? `Date: ${meta.date}` : null,
      '',
      c.content,
    ].filter(Boolean).join('\n');
  }).join('\n\n');

  return { content: [{ type: 'text' as const, text: formatted }] };
}
```

**Step 4: Update `src/server/mcp-server.ts` to use the handler**

Replace the stub `search_project_context` handler:
```typescript
// Add import at top:
import { handleSearchProjectContext } from './tools/search.js';
import { validateJwt, extractBearerToken } from './auth.js';

// Replace stub handler:
server.tool('search_project_context', '...', {
  query: { type: 'string' as const },
  project: { type: 'string' as const, optional: true },
  top_k: { type: 'number' as const, optional: true },
}, async (args, extra) => {
  const token = extractBearerToken(extra?.headers?.authorization);
  const user_email = token ? await validateJwt(token) : 'dev@verygood.ventures';
  return handleSearchProjectContext({ ...args, user_email });
});
```

**Step 5: Run tests**

```bash
npx vitest run test/server/search-tool.test.ts
```
Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/tools/search.ts src/server/mcp-server.ts test/server/search-tool.test.ts
git commit -m "feat: search_project_context tool wired to pgvector search"
```

---

## Phase 2: Ingestion

### Task 10: Connector interface and metadata extraction

**Files:**
- Create: `src/ingestion/connectors/types.ts`
- Create: `src/processing/metadata.ts`
- Create: `test/processing/metadata.test.ts`

**Step 1: Write types**

```typescript
// src/ingestion/connectors/types.ts
export interface RawDocument {
  sourceUrl: string;
  content: string;
  title: string;
  author?: string;
  date: Date;
  artifactType: string;
  sourceTool: string;
}

export interface Source {
  id: string;
  project_id: string;
  connector: string;
  source_url: string;
  source_id: string;
  last_synced_at?: Date;
}

export interface ProjectConfig {
  slack_channels?: string[];
  github_repos?: string[];
  figma_files?: string[];
  jira_projects?: string[];
  notion_pages?: string[];
}

export interface Connector {
  discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]>;
  fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]>;
}
```

**Step 2: Write `src/processing/metadata.ts`**

```typescript
// src/processing/metadata.ts
import type { RawDocument } from '../ingestion/connectors/types.js';

export function buildChunkMetadata(doc: RawDocument, chunkIndex: number): Record<string, unknown> {
  return {
    artifact_type: doc.artifactType,
    source_tool: doc.sourceTool,
    source_url: doc.sourceUrl,
    title: doc.title,
    author: doc.author ?? null,
    date: doc.date.toISOString(),
    chunk_index: chunkIndex,
  };
}
```

**Step 3: Commit**

```bash
git add src/ingestion/connectors/types.ts src/processing/metadata.ts
git commit -m "feat: connector interface types and metadata builder"
```

---

### Task 11: Notion connector

**Files:**
- Create: `src/ingestion/connectors/notion.ts`
- Create: `test/ingestion/connectors/notion.test.ts`

**Step 1: Write failing tests**

```typescript
// test/ingestion/connectors/notion.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@notionhq/client', () => ({
  Client: vi.fn(() => ({
    pages: {
      retrieve: vi.fn().mockResolvedValue({
        id: 'page-1',
        url: 'https://notion.so/page-1',
        properties: {
          title: { title: [{ plain_text: 'Meeting Notes - Feb 2026' }] },
        },
        last_edited_time: '2026-02-01T00:00:00Z',
        created_by: { id: 'user-1' },
      }),
    },
    blocks: {
      children: {
        list: vi.fn().mockResolvedValue({
          results: [
            { type: 'paragraph', paragraph: { rich_text: [{ plain_text: 'We decided to use Supabase.' }] } },
          ],
          has_more: false,
        }),
      },
    },
    search: vi.fn().mockResolvedValue({
      results: [
        {
          id: 'page-1',
          url: 'https://notion.so/page-1',
          object: 'page',
          last_edited_time: '2026-02-01T00:00:00Z',
          properties: { title: { title: [{ plain_text: 'Meeting Notes' }] } },
        },
      ],
    }),
    users: { retrieve: vi.fn().mockResolvedValue({ name: 'Alice' }) },
  })),
}));

import { NotionConnector } from '../../src/ingestion/connectors/notion.js';

describe('NotionConnector', () => {
  let connector: NotionConnector;

  beforeEach(() => {
    connector = new NotionConnector('fake-token');
  });

  it('fetchDocuments returns RawDocuments with content and metadata', async () => {
    const source = {
      id: 'src-1',
      project_id: 'proj-1',
      connector: 'notion',
      source_url: 'https://notion.so/page-1',
      source_id: 'page-1',
    };

    const docs = await connector.fetchDocuments(source);
    expect(docs).toHaveLength(1);
    expect(docs[0].content).toContain('Supabase');
    expect(docs[0].sourceTool).toBe('notion');
    expect(docs[0].artifactType).toBe('meeting_note');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/connectors/notion.test.ts
```

**Step 3: Write `src/ingestion/connectors/notion.ts`**

```typescript
// src/ingestion/connectors/notion.ts
import { Client } from '@notionhq/client';
import type { Connector, RawDocument, Source, ProjectConfig } from './types.js';

const ARTIFACT_TYPE_PATTERNS: [RegExp, string][] = [
  [/meeting|sync|standup|retro|demo|kickoff/i, 'meeting_note'],
  [/prd|product requirement|spec|brief/i, 'prd'],
  [/story|ticket|task|feature/i, 'story'],
  [/adr|decision|architecture/i, 'adr'],
  [/design|figma|ui|ux/i, 'design_spec'],
];

function detectArtifactType(title: string): string {
  for (const [pattern, type] of ARTIFACT_TYPE_PATTERNS) {
    if (pattern.test(title)) return type;
  }
  return 'document';
}

function extractPlainText(blocks: any[]): string {
  return blocks.map(block => {
    const type = block.type;
    const richText = block[type]?.rich_text ?? [];
    return richText.map((r: any) => r.plain_text).join('');
  }).filter(Boolean).join('\n');
}

function getTitle(page: any): string {
  const titleProp = Object.values(page.properties ?? {}).find(
    (p: any) => p.type === 'title'
  ) as any;
  return titleProp?.title?.[0]?.plain_text ?? 'Untitled';
}

export class NotionConnector implements Connector {
  private client: Client;

  constructor(token: string) {
    this.client = new Client({ auth: token });
  }

  async discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]> {
    return (config.notion_pages ?? []).map(url => ({
      connector: 'notion',
      source_url: url,
      source_id: extractNotionId(url),
    }));
  }

  async fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]> {
    // Get all pages under this parent page
    const search = await this.client.search({
      filter: { property: 'object', value: 'page' },
      sort: { direction: 'descending', timestamp: 'last_edited_time' },
    });

    const pages = search.results.filter((page: any) => {
      if (since) {
        return new Date(page.last_edited_time) > since;
      }
      return true;
    });

    const docs: RawDocument[] = [];
    for (const page of pages as any[]) {
      const title = getTitle(page);
      const blocksResponse = await this.client.blocks.children.list({ block_id: page.id });
      const content = extractPlainText(blocksResponse.results as any[]);
      if (!content.trim()) continue;

      docs.push({
        sourceUrl: page.url,
        content,
        title,
        date: new Date(page.last_edited_time),
        artifactType: detectArtifactType(title),
        sourceTool: 'notion',
      });
    }

    return docs;
  }
}

function extractNotionId(url: string): string {
  // URLs like: https://notion.so/workspace/PageName-abc123def456
  const match = url.match(/([a-f0-9]{32})$/);
  return match ? match[1] : url;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/connectors/notion.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/connectors/notion.ts test/ingestion/connectors/notion.test.ts
git commit -m "feat: Notion connector with artifact type detection"
```

---

### Task 12: Project Hub parser

**Files:**
- Create: `src/ingestion/project-hub-parser.ts`
- Create: `test/ingestion/project-hub-parser.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/project-hub-parser.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('@notionhq/client', () => ({
  Client: vi.fn(() => ({
    blocks: {
      children: {
        list: vi.fn().mockResolvedValue({
          results: [
            {
              type: 'heading_2',
              heading_2: { rich_text: [{ plain_text: 'Helpful Links' }] },
            },
            {
              type: 'bulleted_list_item',
              bulleted_list_item: {
                rich_text: [{ plain_text: 'Slack channel' }],
                children: [
                  { type: 'bookmark', bookmark: { url: 'https://verygood.slack.com/channels/proj-alpha' } },
                ],
              },
            },
            {
              type: 'bulleted_list_item',
              bulleted_list_item: {
                rich_text: [{ plain_text: 'GitHub' }],
              },
            },
          ],
          has_more: false,
        }),
      },
    },
  })),
}));

import { parseProjectHub } from '../../src/ingestion/project-hub-parser.js';

describe('parseProjectHub', () => {
  it('extracts slack channel URLs from Helpful Links', async () => {
    const config = await parseProjectHub('https://notion.so/abc123', 'fake-token');
    expect(config.slack_channels).toBeDefined();
    expect(config.slack_channels?.some(u => u.includes('proj-alpha'))).toBe(true);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/project-hub-parser.test.ts
```

**Step 3: Write `src/ingestion/project-hub-parser.ts`**

```typescript
// src/ingestion/project-hub-parser.ts
import { Client } from '@notionhq/client';
import type { ProjectConfig } from './connectors/types.js';

function extractUrls(block: any): string[] {
  const urls: string[] = [];

  // Check rich_text for URLs
  const richText = block[block.type]?.rich_text ?? [];
  for (const rt of richText) {
    if (rt.href) urls.push(rt.href);
    if (rt.text?.link?.url) urls.push(rt.text.link.url);
  }

  // Check bookmark blocks
  if (block.type === 'bookmark') {
    const url = block.bookmark?.url;
    if (url) urls.push(url);
  }

  return urls;
}

function classifyUrl(url: string, config: ProjectConfig): void {
  if (url.includes('slack.com/channels') || url.includes('slack.com/archives')) {
    config.slack_channels = [...(config.slack_channels ?? []), url];
  } else if (url.includes('github.com')) {
    config.github_repos = [...(config.github_repos ?? []), url];
  } else if (url.includes('figma.com')) {
    config.figma_files = [...(config.figma_files ?? []), url];
  } else if (url.includes('atlassian.net') || url.includes('jira')) {
    config.jira_projects = [...(config.jira_projects ?? []), url];
  } else if (url.includes('notion.so')) {
    config.notion_pages = [...(config.notion_pages ?? []), url];
  }
}

async function fetchAllBlocks(client: Client, blockId: string): Promise<any[]> {
  const results: any[] = [];
  let cursor: string | undefined;

  do {
    const response = await client.blocks.children.list({
      block_id: blockId,
      start_cursor: cursor,
    });
    results.push(...response.results);
    cursor = response.has_more ? (response as any).next_cursor : undefined;
  } while (cursor);

  return results;
}

export async function parseProjectHub(hubUrl: string, notionToken: string): Promise<ProjectConfig> {
  const client = new Client({ auth: notionToken });
  const pageId = hubUrl.split('-').pop()?.replace(/[^a-f0-9]/gi, '') ?? hubUrl;
  const config: ProjectConfig = {};

  let inHelpfulLinks = false;
  const blocks = await fetchAllBlocks(client, pageId);

  for (const block of blocks) {
    const type: string = block.type;
    const text = (block[type]?.rich_text ?? []).map((r: any) => r.plain_text).join('');

    if (type.startsWith('heading') && text.toLowerCase().includes('helpful links')) {
      inHelpfulLinks = true;
      continue;
    }

    if (type.startsWith('heading') && inHelpfulLinks) {
      inHelpfulLinks = false;
    }

    if (inHelpfulLinks) {
      const urls = extractUrls(block);
      for (const url of urls) classifyUrl(url, config);
    }
  }

  return config;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/project-hub-parser.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/project-hub-parser.ts test/ingestion/project-hub-parser.test.ts
git commit -m "feat: Project Hub parser extracts connector configs from Notion Helpful Links"
```

---

### Task 13: Sync scheduler and ingestion pipeline

**Files:**
- Create: `src/ingestion/scheduler.ts`
- Create: `test/ingestion/scheduler.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/scheduler.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/storage/queries.js', () => ({
  listSourcesForProject: vi.fn().mockResolvedValue([
    { id: 'src-1', project_id: 'proj-1', connector: 'notion', source_url: 'https://notion.so/abc', source_id: 'abc', last_synced_at: null, sync_status: 'pending' },
  ]),
  updateSourceSyncStatus: vi.fn().mockResolvedValue(undefined),
  deleteChunksBySource: vi.fn().mockResolvedValue(undefined),
  insertChunks: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../src/processing/embedder.js', () => ({
  embed: vi.fn().mockResolvedValue(new Array(384).fill(0)),
}));

import { syncSource } from '../../src/ingestion/scheduler.js';

describe('syncSource', () => {
  it('deletes old chunks and inserts new ones', async () => {
    const { deleteChunksBySource, insertChunks } = await import('../../src/storage/queries.js');

    const mockConnector = {
      discoverSources: vi.fn(),
      fetchDocuments: vi.fn().mockResolvedValue([
        {
          sourceUrl: 'https://notion.so/abc',
          content: 'Some meeting content',
          title: 'Meeting Notes',
          date: new Date(),
          artifactType: 'meeting_note',
          sourceTool: 'notion',
        },
      ]),
    };

    await syncSource({
      source: { id: 'src-1', project_id: 'proj-1', connector: 'notion', source_url: 'https://notion.so/abc', source_id: 'abc' },
      connector: mockConnector,
    });

    expect(deleteChunksBySource).toHaveBeenCalledWith('src-1');
    expect(insertChunks).toHaveBeenCalled();
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/scheduler.test.ts
```

**Step 3: Write `src/ingestion/scheduler.ts`**

```typescript
// src/ingestion/scheduler.ts
import cron from 'node-cron';
import { supabase } from '../storage/supabase.js';
import {
  listSourcesForProject,
  updateSourceSyncStatus,
  deleteChunksBySource,
  insertChunks,
} from '../storage/queries.js';
import { embed } from '../processing/embedder.js';
import { chunk } from '../processing/chunker.js';
import { buildChunkMetadata } from '../processing/metadata.js';
import type { Connector, Source, RawDocument } from './connectors/types.js';
import { env } from '../config/env.js';

export async function syncSource({
  source,
  connector,
}: {
  source: Source;
  connector: Connector;
}): Promise<void> {
  await updateSourceSyncStatus(source.id, 'syncing');

  try {
    const since = source.last_synced_at ? new Date(source.last_synced_at) : undefined;
    const docs: RawDocument[] = await connector.fetchDocuments(source, since);

    // Delete stale chunks for this source, then re-insert
    await deleteChunksBySource(source.id);

    for (const doc of docs) {
      const chunks = chunk(doc.content, doc.artifactType);
      const embeddings = await Promise.all(chunks.map(embed));

      const rows = chunks.map((text, i) => ({
        project_id: source.project_id,
        source_id: source.id,
        content: text,
        embedding: embeddings[i],
        metadata: buildChunkMetadata(doc, i),
      }));

      if (rows.length > 0) await insertChunks(rows);
    }

    await updateSourceSyncStatus(source.id, 'success');
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    await updateSourceSyncStatus(source.id, 'error', msg);
    console.error(`Sync failed for source ${source.id}: ${msg}`);
  }
}

export function startScheduler(
  getConnector: (connectorType: string) => Connector | null
): void {
  const isBusinessHours = () => {
    const now = new Date();
    const hour = now.getHours();
    const day = now.getDay();
    return day >= 1 && day <= 5 && hour >= 8 && hour <= 20;
  };

  const runSync = async () => {
    console.log('Sync cycle starting...');
    const { data: projects, error } = await supabase.from('projects').select('id');
    if (error || !projects) return;

    for (const project of projects) {
      const sources = await listSourcesForProject(project.id);
      for (const source of sources) {
        const connector = getConnector(source.connector);
        if (!connector) {
          console.warn(`No connector for type: ${source.connector}`);
          continue;
        }
        await syncSource({ source, connector });
      }
    }
    console.log('Sync cycle complete.');
  };

  // Business hours: every 15 minutes
  cron.schedule(env.SYNC_CRON, () => {
    if (isBusinessHours()) runSync();
  });

  // Off hours: every hour
  cron.schedule(env.SYNC_CRON_OFF_HOURS, () => {
    if (!isBusinessHours()) runSync();
  });

  console.log('Sync scheduler started.');
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/scheduler.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/scheduler.ts test/ingestion/scheduler.test.ts
git commit -m "feat: sync scheduler with cron-based ingestion pipeline"
```

---

### Task 14: `seed-project.ts` CLI script

**Files:**
- Create: `scripts/seed-project.ts`

**Step 1: Write the script**

```typescript
// scripts/seed-project.ts
import 'dotenv/config';
import { parseArgs } from 'util';
import { parseProjectHub } from '../src/ingestion/project-hub-parser.js';
import { upsertProject, upsertSource } from '../src/storage/queries.js';
import { syncSource } from '../src/ingestion/scheduler.js';
import { NotionConnector } from '../src/ingestion/connectors/notion.js';
import { env } from '../src/config/env.js';

const { values } = parseArgs({
  options: {
    'hub-url': { type: 'string' },
    'name': { type: 'string' },
    'member': { type: 'string', multiple: true },
  },
});

const hubUrl = values['hub-url'];
const name = values['name'];

if (!hubUrl || !name) {
  console.error('Usage: npm run seed -- --hub-url <url> --name <name> [--member email@verygood.ventures]');
  process.exit(1);
}

if (!env.NOTION_API_TOKEN) {
  console.error('NOTION_API_TOKEN is required');
  process.exit(1);
}

console.log(`Onboarding project: ${name}`);
console.log(`Hub URL: ${hubUrl}`);

// 1. Parse the Project Hub
console.log('\n1. Parsing Project Hub...');
const config = await parseProjectHub(hubUrl, env.NOTION_API_TOKEN);
console.log('  Discovered:', JSON.stringify(config, null, 2));

// 2. Create project record
console.log('\n2. Creating project record...');
const projectId = await upsertProject({ name, notion_hub_url: hubUrl, config });
console.log(`  Project ID: ${projectId}`);

// 3. Create source records
console.log('\n3. Creating source records...');
const notionConnector = new NotionConnector(env.NOTION_API_TOKEN);

for (const url of config.notion_pages ?? []) {
  const sourceId = await upsertSource({
    project_id: projectId,
    connector: 'notion',
    source_url: url,
    source_id: url.split('-').pop() ?? url,
  });
  console.log(`  Notion source: ${sourceId}`);

  // 4. Initial ingestion
  console.log(`  Syncing...`);
  await syncSource({
    source: { id: sourceId, project_id: projectId, connector: 'notion', source_url: url, source_id: url.split('-').pop() ?? url },
    connector: notionConnector,
  });
  console.log(`  Done.`);
}

// 5. Add project members
if (values['member']?.length) {
  console.log('\n4. Adding members...');
  const { supabase } = await import('../src/storage/supabase.js');
  for (const email of values['member'] as string[]) {
    await supabase.from('project_members').upsert({ project_id: projectId, user_email: email });
    console.log(`  Added: ${email}`);
  }
}

console.log('\nDone! Project onboarded successfully.');
```

**Step 2: Manual test**

```bash
npm run seed -- \
  --hub-url "https://www.notion.so/verygoodventures/TestProject-Hub-abc123" \
  --name "Test Project" \
  --member "you@verygood.ventures"
```
Expected: Project created, sources discovered, initial sync run.

**Step 3: Commit**

```bash
git add scripts/seed-project.ts
git commit -m "feat: seed-project CLI for onboarding new projects from Notion Hub URL"
```

---

## Phase 3: Additional Connectors

### Task 15: Slack connector

**Files:**
- Create: `src/ingestion/connectors/slack.ts`
- Create: `test/ingestion/connectors/slack.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/connectors/slack.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('@slack/web-api', () => ({
  WebClient: vi.fn(() => ({
    conversations: {
      history: vi.fn().mockResolvedValue({
        ok: true,
        messages: [
          { ts: '1234567890.000001', text: 'Hey team, decided to use Supabase', user: 'U001', thread_ts: undefined, subtype: undefined },
          { ts: '1234567890.000002', text: '', user: 'U002', subtype: 'channel_join' }, // should be filtered out
        ],
        has_more: false,
      }),
      replies: vi.fn().mockResolvedValue({ ok: true, messages: [], has_more: false }),
      info: vi.fn().mockResolvedValue({ ok: true, channel: { name: 'proj-alpha' } }),
    },
    users: {
      info: vi.fn().mockResolvedValue({ ok: true, user: { real_name: 'Alice' } }),
    },
  })),
}));

import { SlackConnector } from '../../src/ingestion/connectors/slack.js';

describe('SlackConnector', () => {
  it('fetches messages, filters bots and joins, returns slack_thread docs', async () => {
    const connector = new SlackConnector('fake-token');
    const source = { id: 'src-1', project_id: 'proj-1', connector: 'slack', source_url: 'https://slack.com/channels/proj-alpha', source_id: 'C001' };

    const docs = await connector.fetchDocuments(source);
    expect(docs).toHaveLength(1);
    expect(docs[0].artifactType).toBe('slack_thread');
    expect(docs[0].content).toContain('Supabase');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/connectors/slack.test.ts
```

**Step 3: Write `src/ingestion/connectors/slack.ts`**

```typescript
// src/ingestion/connectors/slack.ts
import { WebClient } from '@slack/web-api';
import type { Connector, RawDocument, Source, ProjectConfig } from './types.js';

const BOT_SUBTYPES = new Set(['bot_message', 'channel_join', 'channel_leave', 'channel_topic']);

export class SlackConnector implements Connector {
  private client: WebClient;

  constructor(token: string) {
    this.client = new WebClient(token);
  }

  async discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]> {
    const sources = [];
    for (const url of config.slack_channels ?? []) {
      const channelId = extractChannelId(url);
      if (channelId) {
        sources.push({ connector: 'slack', source_url: url, source_id: channelId });
      }
    }
    return sources;
  }

  async fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]> {
    const oldest = since ? String(since.getTime() / 1000) : undefined;

    const channelInfo = await this.client.conversations.info({ channel: source.source_id });
    const channelName = (channelInfo as any).channel?.name ?? source.source_id;

    const response = await this.client.conversations.history({
      channel: source.source_id,
      oldest,
      limit: 200,
    });

    const messages = ((response as any).messages ?? []).filter((m: any) =>
      m.text?.trim() &&
      !BOT_SUBTYPES.has(m.subtype) &&
      !m.bot_id &&
      !/^<:.+:>$/.test(m.text.trim()) // skip pure emoji reactions
    );

    const docs: RawDocument[] = [];
    for (const msg of messages) {
      if (msg.thread_ts && msg.thread_ts !== msg.ts) continue; // skip thread replies (fetched below)

      let content = msg.text;
      let authorName: string | undefined;

      // Fetch author name
      try {
        const userInfo = await this.client.users.info({ user: msg.user });
        authorName = (userInfo as any).user?.real_name;
      } catch {}

      // If it's a thread parent, fetch replies
      if (msg.reply_count && msg.reply_count > 0) {
        const replies = await this.client.conversations.replies({
          channel: source.source_id,
          ts: msg.ts,
        });
        const replyTexts = ((replies as any).messages ?? [])
          .slice(1) // skip parent
          .filter((r: any) => r.text?.trim())
          .map((r: any) => `> ${r.text}`);
        if (replyTexts.length > 0) content += '\n' + replyTexts.join('\n');
      }

      docs.push({
        sourceUrl: `https://slack.com/archives/${source.source_id}/p${msg.ts.replace('.', '')}`,
        content,
        title: `#${channelName} thread`,
        author: authorName,
        date: new Date(parseFloat(msg.ts) * 1000),
        artifactType: 'slack_thread',
        sourceTool: 'slack',
      });
    }

    return docs;
  }
}

function extractChannelId(url: string): string | null {
  const match = url.match(/\/([CG][A-Z0-9]+)/);
  return match ? match[1] : null;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/connectors/slack.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/connectors/slack.ts test/ingestion/connectors/slack.test.ts
git commit -m "feat: Slack connector with thread fetching and bot/join message filtering"
```

---

### Task 16: GitHub connector

**Files:**
- Create: `src/ingestion/connectors/github.ts`
- Create: `test/ingestion/connectors/github.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/connectors/github.test.ts
import { describe, it, expect, vi } from 'vitest';

vi.mock('@octokit/rest', () => ({
  Octokit: vi.fn(() => ({
    repos: {
      getContent: vi.fn().mockResolvedValue({
        data: { content: Buffer.from('# Project README\nThis project uses Supabase.').toString('base64'), encoding: 'base64' },
      }),
    },
    pulls: {
      list: vi.fn().mockResolvedValue({
        data: [
          { number: 1, title: 'Add auth middleware', body: 'Implements JWT validation', user: { login: 'alice' }, updated_at: '2026-02-01T00:00:00Z', html_url: 'https://github.com/vgv/repo/pull/1' },
        ],
      }),
    },
    issues: {
      list: vi.fn().mockResolvedValue({ data: [] }),
    },
  })),
}));

import { GitHubConnector } from '../../src/ingestion/connectors/github.js';

describe('GitHubConnector', () => {
  it('fetches README and PRs as RawDocuments', async () => {
    const connector = new GitHubConnector('fake-pat');
    const source = { id: 'src-1', project_id: 'proj-1', connector: 'github', source_url: 'https://github.com/vgv/repo', source_id: 'vgv/repo' };

    const docs = await connector.fetchDocuments(source);
    expect(docs.length).toBeGreaterThan(0);

    const readme = docs.find(d => d.title.includes('README'));
    expect(readme?.content).toContain('Supabase');
    expect(readme?.artifactType).toBe('document');

    const pr = docs.find(d => d.artifactType === 'pr');
    expect(pr?.content).toContain('JWT validation');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/connectors/github.test.ts
```

**Step 3: Write `src/ingestion/connectors/github.ts`**

```typescript
// src/ingestion/connectors/github.ts
import { Octokit } from '@octokit/rest';
import type { Connector, RawDocument, Source, ProjectConfig } from './types.js';

const IMPORTANT_FILES = ['README.md', 'CLAUDE.md', 'AGENTS.md'];
const ADR_PATHS = ['docs/decisions', 'adr', 'docs/adr'];

export class GitHubConnector implements Connector {
  private octokit: Octokit;

  constructor(token: string) {
    this.octokit = new Octokit({ auth: token });
  }

  async discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]> {
    return (config.github_repos ?? []).map(url => ({
      connector: 'github',
      source_url: url,
      source_id: extractRepoSlug(url),
    }));
  }

  async fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]> {
    const [owner, repo] = source.source_id.split('/');
    const docs: RawDocument[] = [];

    // Fetch key files
    for (const filename of IMPORTANT_FILES) {
      try {
        const { data } = await this.octokit.repos.getContent({ owner, repo, path: filename });
        const content = Buffer.from((data as any).content, 'base64').toString('utf8');
        docs.push({
          sourceUrl: `https://github.com/${source.source_id}/blob/main/${filename}`,
          content,
          title: filename,
          date: new Date(),
          artifactType: 'document',
          sourceTool: 'github',
        });
      } catch {} // File doesn't exist — skip
    }

    // Fetch PRs
    const { data: prs } = await this.octokit.pulls.list({
      owner,
      repo,
      state: 'all',
      sort: 'updated',
      direction: 'desc',
      per_page: 50,
      ...(since ? { since: since.toISOString() } : {}),
    });

    for (const pr of prs) {
      if (!pr.body?.trim()) continue;
      docs.push({
        sourceUrl: pr.html_url,
        content: `# ${pr.title}\n\n${pr.body}`,
        title: `PR #${pr.number}: ${pr.title}`,
        author: pr.user?.login,
        date: new Date(pr.updated_at),
        artifactType: 'pr',
        sourceTool: 'github',
      });
    }

    return docs;
  }
}

function extractRepoSlug(url: string): string {
  // https://github.com/owner/repo → owner/repo
  const match = url.match(/github\.com\/([^/]+\/[^/]+)/);
  return match ? match[1] : url;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/connectors/github.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/connectors/github.ts test/ingestion/connectors/github.test.ts
git commit -m "feat: GitHub connector for README, CLAUDE.md, and PR descriptions"
```

---

### Task 17: Figma connector

**Files:**
- Create: `src/ingestion/connectors/figma.ts`
- Create: `test/ingestion/connectors/figma.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/connectors/figma.test.ts
import { describe, it, expect, vi } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: vi.fn().mockResolvedValue({
    name: 'Design System',
    document: {
      name: 'Document',
      children: [
        {
          name: 'Components',
          type: 'FRAME',
          children: [
            { name: 'Button', type: 'COMPONENT', description: 'Primary button component' },
            { name: 'Input', type: 'COMPONENT', description: 'Text input field' },
          ],
        },
      ],
    },
  }),
} as any);

import { FigmaConnector } from '../../src/ingestion/connectors/figma.js';

describe('FigmaConnector', () => {
  it('extracts component metadata as design_spec documents', async () => {
    const connector = new FigmaConnector('fake-token');
    const source = { id: 'src-1', project_id: 'proj-1', connector: 'figma', source_url: 'https://figma.com/file/ABC123/Design-System', source_id: 'ABC123' };

    const docs = await connector.fetchDocuments(source);
    expect(docs.length).toBeGreaterThan(0);
    expect(docs[0].artifactType).toBe('design_spec');
    expect(docs[0].content).toContain('Button');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/connectors/figma.test.ts
```

**Step 3: Write `src/ingestion/connectors/figma.ts`**

```typescript
// src/ingestion/connectors/figma.ts
import type { Connector, RawDocument, Source, ProjectConfig } from './types.js';

const FIGMA_API = 'https://api.figma.com/v1';

export class FigmaConnector implements Connector {
  private token: string;

  constructor(token: string) {
    this.token = token;
  }

  async discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]> {
    return (config.figma_files ?? []).map(url => ({
      connector: 'figma',
      source_url: url,
      source_id: extractFileKey(url),
    }));
  }

  async fetchDocuments(source: Source): Promise<RawDocument[]> {
    // Figma: full resync each cycle (no reliable incremental API)
    const response = await fetch(`${FIGMA_API}/files/${source.source_id}`, {
      headers: { 'X-Figma-Token': this.token },
    });

    if (!response.ok) throw new Error(`Figma API error: ${response.status}`);
    const file = await response.json() as any;

    const docs: RawDocument[] = [];
    extractComponents(file.document, source.source_id, file.name, docs);

    return docs;
  }
}

function extractComponents(node: any, fileKey: string, fileName: string, docs: RawDocument[]): void {
  if (node.type === 'COMPONENT' || node.type === 'COMPONENT_SET') {
    const content = [
      `Component: ${node.name}`,
      node.description ? `Description: ${node.description}` : null,
      node.type === 'COMPONENT_SET' ? `Variants: ${node.children?.map((c: any) => c.name).join(', ')}` : null,
    ].filter(Boolean).join('\n');

    docs.push({
      sourceUrl: `https://figma.com/file/${fileKey}?node-id=${node.id}`,
      content,
      title: `${fileName} — ${node.name}`,
      date: new Date(),
      artifactType: 'design_spec',
      sourceTool: 'figma',
    });
  }

  for (const child of node.children ?? []) {
    extractComponents(child, fileKey, fileName, docs);
  }
}

function extractFileKey(url: string): string {
  const match = url.match(/figma\.com\/(?:file|design)\/([a-zA-Z0-9]+)/);
  return match ? match[1] : url;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/connectors/figma.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/connectors/figma.ts test/ingestion/connectors/figma.test.ts
git commit -m "feat: Figma connector extracting component metadata and design tokens"
```

---

### Task 18: Atlassian (Jira) connector

**Files:**
- Create: `src/ingestion/connectors/atlassian.ts`
- Create: `test/ingestion/connectors/atlassian.test.ts`

**Step 1: Write failing test**

```typescript
// test/ingestion/connectors/atlassian.test.ts
import { describe, it, expect, vi } from 'vitest';

global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: vi.fn().mockResolvedValue({
    issues: [
      {
        key: 'PROJ-1',
        fields: {
          summary: 'Implement auth middleware',
          description: { content: [{ content: [{ text: 'We need JWT validation.' }] }] },
          status: { name: 'In Progress' },
          assignee: { displayName: 'Alice' },
          updated: '2026-02-01T00:00:00Z',
        },
      },
    ],
    total: 1,
  }),
} as any);

import { AtlassianConnector } from '../../src/ingestion/connectors/atlassian.js';

describe('AtlassianConnector', () => {
  it('fetches Jira issues as RawDocuments', async () => {
    const connector = new AtlassianConnector({
      token: 'fake-token',
      email: 'user@verygood.ventures',
      domain: 'verygoodventures.atlassian.net',
    });
    const source = { id: 'src-1', project_id: 'proj-1', connector: 'atlassian', source_url: 'https://verygoodventures.atlassian.net/jira/software/projects/PROJ', source_id: 'PROJ' };

    const docs = await connector.fetchDocuments(source);
    expect(docs.length).toBeGreaterThan(0);
    expect(docs[0].artifactType).toBe('issue');
    expect(docs[0].content).toContain('auth middleware');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
npx vitest run test/ingestion/connectors/atlassian.test.ts
```

**Step 3: Write `src/ingestion/connectors/atlassian.ts`**

```typescript
// src/ingestion/connectors/atlassian.ts
import type { Connector, RawDocument, Source, ProjectConfig } from './types.js';

interface AtlassianConfig {
  token: string;
  email: string;
  domain: string;
}

function adfToText(node: any): string {
  if (!node) return '';
  if (node.type === 'text') return node.text ?? '';
  return (node.content ?? []).map(adfToText).join('');
}

export class AtlassianConnector implements Connector {
  private config: AtlassianConfig;

  constructor(config: AtlassianConfig) {
    this.config = config;
  }

  async discoverSources(config: ProjectConfig): Promise<Omit<Source, 'id' | 'project_id'>[]> {
    return (config.jira_projects ?? []).map(url => ({
      connector: 'atlassian',
      source_url: url,
      source_id: extractProjectKey(url),
    }));
  }

  async fetchDocuments(source: Source, since?: Date): Promise<RawDocument[]> {
    const { domain, email, token } = this.config;
    const auth = Buffer.from(`${email}:${token}`).toString('base64');

    let jql = `project = "${source.source_id}" ORDER BY updated DESC`;
    if (since) {
      const dateStr = since.toISOString().split('T')[0];
      jql = `project = "${source.source_id}" AND updated > "${dateStr}" ORDER BY updated DESC`;
    }

    const response = await fetch(
      `https://${domain}/rest/api/3/search?jql=${encodeURIComponent(jql)}&maxResults=100&fields=summary,description,status,assignee,updated,comment`,
      { headers: { Authorization: `Basic ${auth}`, 'Content-Type': 'application/json' } }
    );

    if (!response.ok) throw new Error(`Jira API error: ${response.status}`);
    const data = await response.json() as any;

    return (data.issues ?? []).map((issue: any): RawDocument => {
      const desc = adfToText(issue.fields.description);
      const comments = (issue.fields.comment?.comments ?? [])
        .map((c: any) => `[${c.author?.displayName}]: ${adfToText(c.body)}`)
        .join('\n');

      const content = [
        `Issue: ${issue.key} — ${issue.fields.summary}`,
        `Status: ${issue.fields.status?.name}`,
        desc ? `\nDescription:\n${desc}` : null,
        comments ? `\nComments:\n${comments}` : null,
      ].filter(Boolean).join('\n');

      return {
        sourceUrl: `https://${domain}/browse/${issue.key}`,
        content,
        title: `${issue.key}: ${issue.fields.summary}`,
        author: issue.fields.assignee?.displayName,
        date: new Date(issue.fields.updated),
        artifactType: 'issue',
        sourceTool: 'atlassian',
      };
    });
  }
}

function extractProjectKey(url: string): string {
  const match = url.match(/projects\/([A-Z][A-Z0-9]+)/);
  return match ? match[1] : url;
}
```

**Step 4: Run tests**

```bash
npx vitest run test/ingestion/connectors/atlassian.test.ts
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/ingestion/connectors/atlassian.ts test/ingestion/connectors/atlassian.test.ts
git commit -m "feat: Atlassian/Jira connector with JQL incremental sync and ADF text extraction"
```

---

## Phase 4: Polish

### Task 19: `list_sources` and `ingest_document` tools

**Files:**
- Create: `src/server/tools/list-sources.ts`
- Create: `src/server/tools/ingest.ts`
- Modify: `src/server/mcp-server.ts`

**Step 1: Write `src/server/tools/list-sources.ts`**

```typescript
// src/server/tools/list-sources.ts
import { listSourcesForProject, listProjectsForUser, getProjectByName } from '../../storage/queries.js';

export async function handleListSources(args: { project?: string; user_email: string }) {
  const { project, user_email } = args;

  let projectId: string;
  if (project) {
    const proj = await getProjectByName(project);
    if (!proj) throw new Error(`Project not found: ${project}`);
    projectId = proj.id;
  } else {
    const projects = await listProjectsForUser(user_email);
    if (projects.length === 0) throw new Error('No projects found for user');
    projectId = projects[0].id;
  }

  const sources = await listSourcesForProject(projectId);
  if (sources.length === 0) {
    return { content: [{ type: 'text' as const, text: 'No sources indexed yet.' }] };
  }

  const lines = sources.map((s: any) =>
    `• [${s.connector}] ${s.source_url}\n  Status: ${s.sync_status} | Last sync: ${s.last_synced_at ?? 'never'}${s.sync_error ? `\n  Error: ${s.sync_error}` : ''}`
  );

  return { content: [{ type: 'text' as const, text: lines.join('\n\n') }] };
}
```

**Step 2: Write `src/server/tools/ingest.ts`**

```typescript
// src/server/tools/ingest.ts
import { embed } from '../../processing/embedder.js';
import { chunk } from '../../processing/chunker.js';
import { upsertSource, insertChunks, getProjectByName } from '../../storage/queries.js';
import { buildChunkMetadata } from '../../processing/metadata.js';

export async function handleIngestDocument(args: {
  project: string;
  content?: string;
  url?: string;
  artifact_type?: string;
}) {
  const { project, content, url, artifact_type = 'document' } = args;

  if (!content && !url) throw new Error('Either content or url is required');

  const proj = await getProjectByName(project);
  if (!proj) throw new Error(`Project not found: ${project}`);

  let text = content ?? '';
  if (url && !content) {
    const response = await fetch(url);
    text = await response.text();
  }

  const sourceId = await upsertSource({
    project_id: proj.id,
    connector: 'manual',
    source_url: url ?? 'inline',
    source_id: url ?? `manual-${Date.now()}`,
  });

  const chunks = chunk(text, artifact_type);
  const embeddings = await Promise.all(chunks.map(embed));

  const doc = {
    sourceUrl: url ?? 'inline',
    content: text,
    title: url ?? 'Manual document',
    date: new Date(),
    artifactType: artifact_type,
    sourceTool: 'manual',
  };

  await insertChunks(chunks.map((c, i) => ({
    project_id: proj.id,
    source_id: sourceId,
    content: c,
    embedding: embeddings[i],
    metadata: buildChunkMetadata(doc, i),
  })));

  return {
    content: [{
      type: 'text' as const,
      text: `Indexed ${chunks.length} chunk(s) from ${url ?? 'inline content'} into project "${project}".`,
    }],
  };
}
```

**Step 3: Wire into `src/server/mcp-server.ts`**

Replace stub handlers with:
```typescript
import { handleListSources } from './tools/list-sources.js';
import { handleIngestDocument } from './tools/ingest.js';

// Replace stub list_sources:
server.tool('list_sources', '...', { project: { type: 'string' as const, optional: true } }, async (args, extra) => {
  const token = extractBearerToken(extra?.headers?.authorization);
  const user_email = token ? await validateJwt(token) : 'dev@verygood.ventures';
  return handleListSources({ ...args, user_email });
});

// Replace stub ingest_document:
server.tool('ingest_document', '...', {
  project: { type: 'string' as const },
  content: { type: 'string' as const, optional: true },
  url: { type: 'string' as const, optional: true },
  artifact_type: { type: 'string' as const, optional: true },
}, async (args) => {
  return handleIngestDocument(args);
});
```

**Step 4: Commit**

```bash
git add src/server/tools/list-sources.ts src/server/tools/ingest.ts src/server/mcp-server.ts
git commit -m "feat: list_sources and ingest_document MCP tools"
```

---

### Task 20: Wire up scheduler with all connectors in `src/index.ts`

**Files:**
- Modify: `src/index.ts`

**Step 1: Update `src/index.ts`**

```typescript
// src/index.ts
import 'dotenv/config';
import { createMcpServer, startHttpServer } from './server/mcp-server.js';
import { startScheduler } from './ingestion/scheduler.js';
import { NotionConnector } from './ingestion/connectors/notion.js';
import { SlackConnector } from './ingestion/connectors/slack.js';
import { GitHubConnector } from './ingestion/connectors/github.js';
import { FigmaConnector } from './ingestion/connectors/figma.js';
import { AtlassianConnector } from './ingestion/connectors/atlassian.js';
import { env } from './config/env.js';
import type { Connector } from './ingestion/connectors/types.js';

const connectors: Record<string, Connector> = {
  notion: new NotionConnector(env.NOTION_API_TOKEN ?? ''),
  slack: new SlackConnector(env.SLACK_BOT_TOKEN ?? ''),
  github: new GitHubConnector(env.GITHUB_PAT ?? ''),
  figma: new FigmaConnector(env.FIGMA_API_TOKEN ?? ''),
  atlassian: new AtlassianConnector({
    token: env.ATLASSIAN_API_TOKEN ?? '',
    email: env.ATLASSIAN_EMAIL ?? '',
    domain: env.ATLASSIAN_DOMAIN ?? '',
  }),
};

const server = createMcpServer();
await startHttpServer(server);
startScheduler(type => connectors[type] ?? null);
```

**Step 2: Run all tests**

```bash
npx vitest run
```
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add src/index.ts
git commit -m "feat: wire all connectors into scheduler on startup"
```

---

### Task 21: Dockerfile and docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Write `Dockerfile`**

```dockerfile
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --production

COPY dist/ ./dist/

ENV TRANSFORMERS_CACHE=/app/.cache/transformers

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

CMD ["node", "dist/index.js"]
```

**Step 2: Write `docker-compose.yml`**

```yaml
version: "3.8"
services:
  rag-service:
    build: .
    ports:
      - "3000:3000"
    env_file:
      - .env
    volumes:
      - transformer-cache:/app/.cache/transformers
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  transformer-cache:
```

**Step 3: Build and smoke test**

```bash
npm run build
docker-compose up --build -d
sleep 10
curl http://localhost:3000/health
# Expected: {"status":"ok","service":"vgv-project-rag"}
docker-compose down
```

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Dockerfile and docker-compose for VPS deployment"
```

---

### Task 22: Run full test suite and verify

**Step 1: Run all tests**

```bash
npx vitest run --reporter=verbose
```
Expected: All tests PASS with no failures.

**Step 2: Check TypeScript compiles cleanly**

```bash
npm run build
```
Expected: No TypeScript errors, `dist/` directory populated.

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify build and test suite passing"
```

---

## End-to-End Verification Checklist

After completing all phases, verify manually:

1. **Supabase setup**
   - Run `001_initial_schema.sql` in Supabase SQL Editor
   - Enable Google Auth provider, restrict to `@verygood.ventures`
   - Confirm `match_chunks` RPC exists

2. **Seed a project**
   ```bash
   cp .env.example .env
   # Fill in real credentials
   npm run seed -- --hub-url "https://notion.so/..." --name "My Project" --member "you@verygood.ventures"
   ```

3. **Query from Claude Code**
   - Add `{ "vgv-project-rag": { "url": "http://localhost:3000/mcp" } }` to Claude MCP config
   - Ask: `search_project_context("how does auth work")`
   - Verify results reference real Notion pages

4. **Check sync is running**
   ```bash
   npm run dev
   # Watch logs — sync cycle should fire every 15min
   ```

5. **Docker deployment**
   ```bash
   docker-compose up --build
   ```
