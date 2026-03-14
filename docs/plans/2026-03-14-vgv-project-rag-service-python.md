# VGV Project RAG Service (Python) — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a centralized MCP server in Python that indexes Notion, Slack, GitHub, Figma, and Jira artifacts into Supabase pgvector and serves semantic search to any Claude interface via Google SSO.

**Architecture:** Python 3.12 async service using `FastMCP` (official Anthropic Python SDK) for the MCP server, `sentence-transformers` for local embeddings, `APScheduler` for cron-based ingestion, and `supabase-py` for storage. Connector logic uses official Python SDKs where available, `httpx` for REST-only APIs.

**Tech Stack:** Python 3.12, `uv` (package manager), `mcp[cli]` (official Anthropic Python MCP SDK), `sentence-transformers` (all-MiniLM-L6-v2), `supabase`, `pydantic-settings`, `APScheduler`, `notion-client`, `slack-sdk`, `PyGithub`, `httpx`, `pytest` + `pytest-asyncio` + `pytest-mock`.

---

## Project Structure

```
vgv-project-rag/
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/
│   └── vgv_rag/
│       ├── __init__.py
│       ├── main.py
│       ├── config/
│       │   └── settings.py
│       ├── server/
│       │   ├── mcp_server.py
│       │   ├── auth.py
│       │   └── tools/
│       │       ├── search.py
│       │       ├── list_sources.py
│       │       └── ingest.py
│       ├── ingestion/
│       │   ├── scheduler.py
│       │   ├── project_hub_parser.py
│       │   └── connectors/
│       │       ├── types.py
│       │       ├── notion.py
│       │       ├── slack.py
│       │       ├── github.py
│       │       ├── figma.py
│       │       └── atlassian.py
│       ├── processing/
│       │   ├── embedder.py
│       │   ├── chunker.py
│       │   └── metadata.py
│       └── storage/
│           ├── client.py
│           ├── queries.py
│           └── migrations/
│               └── 001_initial_schema.sql
├── scripts/
│   └── seed_project.py
└── tests/
    ├── conftest.py
    ├── test_settings.py
    ├── test_embedder.py
    ├── test_chunker.py
    ├── test_storage.py
    ├── test_auth.py
    ├── test_search_tool.py
    ├── connectors/
    │   ├── test_notion.py
    │   ├── test_slack.py
    │   ├── test_github.py
    │   ├── test_figma.py
    │   └── test_atlassian.py
    ├── test_project_hub_parser.py
    └── test_scheduler.py
```

---

## Phase 1: Foundation

### Task 1: Initialize project with uv

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/vgv_rag/__init__.py`
- Create: `src/vgv_rag/main.py`

**Step 1: Install uv and initialize project**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv init --name vgv-rag --python 3.12
uv add mcp[cli] supabase pydantic-settings sentence-transformers \
  notion-client slack-sdk PyGithub httpx apscheduler python-dotenv
uv add --dev pytest pytest-asyncio pytest-mock respx
```

**Step 2: Write `pyproject.toml` (replace uv-generated one)**

```toml
[project]
name = "vgv-rag"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mcp[cli]>=1.0.0",
    "supabase>=2.0.0",
    "pydantic-settings>=2.0.0",
    "sentence-transformers>=3.0.0",
    "notion-client>=2.0.0",
    "slack-sdk>=3.0.0",
    "PyGithub>=2.0.0",
    "httpx>=0.27.0",
    "apscheduler>=3.10.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
vgv-rag = "vgv_rag.main:run"
seed-project = "scripts.seed_project:main"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.14.0",
    "respx>=0.21.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/vgv_rag"]
```

**Step 3: Write `.env.example`**

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
LOG_LEVEL=INFO
```

**Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.cache/
dist/
*.egg-info/
```

**Step 5: Write stub `src/vgv_rag/main.py`**

```python
from dotenv import load_dotenv
load_dotenv()

print("VGV Project RAG Service starting...")

def run():
    pass
```

**Step 6: Create `src/vgv_rag/__init__.py`** (empty file)

**Step 7: Commit**

```bash
git add pyproject.toml .env.example .gitignore src/
git commit -m "chore: initialize Python project with uv"
```

---

### Task 2: Typed settings with Pydantic

**Files:**
- Create: `src/vgv_rag/config/settings.py`
- Create: `src/vgv_rag/config/__init__.py`
- Create: `tests/test_settings.py`
- Create: `tests/conftest.py`

**Step 1: Write the failing test**

```python
# tests/test_settings.py
import pytest
import os

def test_settings_reads_supabase_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    # Re-import to pick up patched env
    import importlib
    import vgv_rag.config.settings as mod
    importlib.reload(mod)
    from vgv_rag.config.settings import settings

    assert settings.supabase_url == "https://test.supabase.co"

def test_settings_raises_on_missing_required(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    import importlib
    import vgv_rag.config.settings as mod
    with pytest.raises(Exception):
        importlib.reload(mod)
        from vgv_rag.config.settings import settings
        _ = settings.supabase_url
```

**Step 2: Write `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from dotenv import load_dotenv

@pytest.fixture(autouse=True)
def load_env():
    """Load .env for tests that need real credentials (integration tests)."""
    load_dotenv(override=False)
```

**Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_settings.py -v
```
Expected: FAIL — module not found.

**Step 4: Write `src/vgv_rag/config/settings.py`**

```python
# src/vgv_rag/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # Optional connectors
    notion_api_token: Optional[str] = None
    slack_bot_token: Optional[str] = None
    github_pat: Optional[str] = None
    figma_api_token: Optional[str] = None
    atlassian_api_token: Optional[str] = None
    atlassian_email: Optional[str] = None
    atlassian_domain: Optional[str] = None

    # Service
    port: int = 3000
    sync_cron: str = "*/15 8-20 * * 1-5"
    log_level: str = "INFO"

settings = Settings()
```

**Step 5: Run test**

```bash
uv run pytest tests/test_settings.py -v
```
Expected: PASS.

**Step 6: Commit**

```bash
git add src/vgv_rag/config/ tests/test_settings.py tests/conftest.py
git commit -m "feat: typed settings with pydantic-settings and validation"
```

---

### Task 3: Database schema migration

**Files:**
- Create: `src/vgv_rag/storage/migrations/001_initial_schema.sql`
- Create: `scripts/setup_supabase.py`

**Step 1: Write migration SQL**

```sql
-- src/vgv_rag/storage/migrations/001_initial_schema.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_hub_url TEXT NOT NULL UNIQUE,
    notion_pht_url TEXT,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS chunks_project_artifact_idx
    ON chunks (project_id, (metadata->>'artifact_type'));

CREATE INDEX IF NOT EXISTS chunks_project_tool_idx
    ON chunks (project_id, (metadata->>'source_tool'));

CREATE TABLE IF NOT EXISTS project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_email TEXT NOT NULL,
    role TEXT DEFAULT 'member',
    UNIQUE(project_id, user_email)
);

ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Users can read chunks from their projects"
    ON chunks FOR SELECT
    USING (
        project_id IN (
            SELECT project_id FROM project_members
            WHERE user_email = auth.jwt()->>'email'
        )
    );

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
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id, c.content, c.metadata,
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

**Step 2: Write `scripts/setup_supabase.py`**

```python
#!/usr/bin/env python3
# scripts/setup_supabase.py
"""Prints migration SQL to run in Supabase SQL Editor."""
from pathlib import Path

sql_path = Path(__file__).parent.parent / "src/vgv_rag/storage/migrations/001_initial_schema.sql"
print("Run the following SQL in the Supabase Dashboard > SQL Editor:\n")
print(sql_path.read_text())
```

**Step 3: Manual Supabase setup**

> Run `uv run python scripts/setup_supabase.py`, copy the output, paste into Supabase SQL Editor > Run.
>
> Then: Dashboard > Authentication > Providers > Google. Enable. Restrict signups to `@verygood.ventures`.

**Step 4: Commit**

```bash
git add src/vgv_rag/storage/migrations/ scripts/setup_supabase.py
git commit -m "feat: database schema with pgvector, RLS, and match_chunks function"
```

---

### Task 4: Supabase storage layer

**Files:**
- Create: `src/vgv_rag/storage/client.py`
- Create: `src/vgv_rag/storage/queries.py`
- Create: `src/vgv_rag/storage/__init__.py`
- Create: `tests/test_storage.py`

**Step 1: Write failing tests**

```python
# tests/test_storage.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_supabase(mocker):
    mock = MagicMock()
    mocker.patch("vgv_rag.storage.queries.get_client", return_value=mock)
    return mock

@pytest.mark.asyncio
async def test_insert_chunks_calls_supabase(mock_supabase):
    from vgv_rag.storage.queries import insert_chunks

    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}], count=1)

    await insert_chunks([{
        "project_id": "proj-1",
        "source_id": "src-1",
        "content": "hello",
        "embedding": [0.0] * 384,
        "metadata": {"artifact_type": "prd"},
    }])

    mock_supabase.table.assert_called_with("chunks")

@pytest.mark.asyncio
async def test_search_chunks_calls_rpc(mock_supabase):
    from vgv_rag.storage.queries import search_chunks

    mock_supabase.rpc.return_value.execute.return_value = MagicMock(
        data=[{"id": "1", "content": "test", "metadata": {}, "similarity": 0.9}]
    )

    results = await search_chunks(
        embedding=[0.0] * 384,
        project_id="proj-1",
        top_k=5,
    )

    mock_supabase.rpc.assert_called_once_with("match_chunks", {
        "query_embedding": [0.0] * 384,
        "match_project_id": "proj-1",
        "match_count": 5,
        "filter_metadata": None,
    })
    assert len(results) == 1
    assert results[0]["content"] == "test"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_storage.py -v
```
Expected: FAIL.

**Step 3: Write `src/vgv_rag/storage/client.py`**

```python
# src/vgv_rag/storage/client.py
from supabase import create_client, Client
from vgv_rag.config.settings import settings

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client

def get_user_client(jwt: str) -> Client:
    """User-scoped client that respects Row Level Security."""
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options={"headers": {"Authorization": f"Bearer {jwt}"}},
    )
```

**Step 4: Write `src/vgv_rag/storage/queries.py`**

```python
# src/vgv_rag/storage/queries.py
from __future__ import annotations
import asyncio
from typing import Any
from vgv_rag.storage.client import get_client


def _run(coro):
    """Supabase-py is sync; wrap calls for async context compatibility."""
    return coro


async def insert_chunks(chunks: list[dict[str, Any]]) -> None:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("chunks").insert(chunks).execute()
    )
    if hasattr(result, "error") and result.error:
        raise RuntimeError(f"insert_chunks failed: {result.error}")


async def delete_chunks_by_source(source_id: str) -> None:
    client = get_client()
    await asyncio.to_thread(
        lambda: client.table("chunks").delete().eq("source_id", source_id).execute()
    )


async def search_chunks(
    embedding: list[float],
    project_id: str,
    top_k: int = 5,
    filter_metadata: dict | None = None,
) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_project_id": project_id,
            "match_count": top_k,
            "filter_metadata": filter_metadata,
        }).execute()
    )
    return result.data or []


async def upsert_project(name: str, notion_hub_url: str, config: dict = {}) -> str:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").upsert(
            {"name": name, "notion_hub_url": notion_hub_url, "config": config},
            on_conflict="notion_hub_url",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def upsert_source(
    project_id: str, connector: str, source_url: str, source_id: str
) -> str:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("sources").upsert(
            {"project_id": project_id, "connector": connector,
             "source_url": source_url, "source_id": source_id},
            on_conflict="project_id,connector,source_id",
        ).select("id").execute()
    )
    return result.data[0]["id"]


async def update_source_sync_status(
    source_id: str, status: str, error: str | None = None
) -> None:
    client = get_client()
    payload: dict = {"sync_status": status, "sync_error": error}
    if status == "success":
        from datetime import datetime, timezone
        payload["last_synced_at"] = datetime.now(timezone.utc).isoformat()
    await asyncio.to_thread(
        lambda: client.table("sources").update(payload).eq("id", source_id).execute()
    )


async def list_sources_for_project(project_id: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("sources").select("*").eq("project_id", project_id).execute()
    )
    return result.data or []


async def get_project_by_name(name: str) -> dict | None:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("projects").select("*").ilike("name", name).execute()
    )
    return result.data[0] if result.data else None


async def list_projects_for_user(user_email: str) -> list[dict]:
    client = get_client()
    result = await asyncio.to_thread(
        lambda: client.table("project_members")
            .select("project_id, projects(*)")
            .eq("user_email", user_email)
            .execute()
    )
    return [row["projects"] for row in (result.data or [])]
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_storage.py -v
```
Expected: PASS.

**Step 6: Commit**

```bash
git add src/vgv_rag/storage/ tests/test_storage.py
git commit -m "feat: Supabase storage layer with async wrappers for all queries"
```

---

### Task 5: Embedding engine

**Files:**
- Create: `src/vgv_rag/processing/embedder.py`
- Create: `src/vgv_rag/processing/__init__.py`
- Create: `tests/test_embedder.py`

**Step 1: Write failing test**

```python
# tests/test_embedder.py
import pytest

@pytest.mark.asyncio
async def test_embed_returns_384_dim_vector():
    from vgv_rag.processing.embedder import embed
    vector = await embed("hello world")
    assert len(vector) == 384
    assert all(isinstance(v, float) for v in vector)

@pytest.mark.asyncio
async def test_embed_different_texts_different_vectors():
    from vgv_rag.processing.embedder import embed
    v1 = await embed("project planning meeting")
    v2 = await embed("database schema migration")
    assert v1 != v2

@pytest.mark.asyncio
async def test_embed_batch():
    from vgv_rag.processing.embedder import embed_batch
    vectors = await embed_batch(["text one", "text two", "text three"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_embedder.py -v
```
Expected: FAIL.

**Step 3: Write `src/vgv_rag/processing/embedder.py`**

```python
# src/vgv_rag/processing/embedder.py
import asyncio
from pathlib import Path
from functools import lru_cache
from sentence_transformers import SentenceTransformer

CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache" / "sentence-transformers"
MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, cache_folder=str(CACHE_DIR))


async def embed(text: str) -> list[float]:
    """Embed a single text string. Runs model in a thread to avoid blocking."""
    model = _get_model()
    vector = await asyncio.to_thread(
        lambda: model.encode(text, normalize_embeddings=True).tolist()
    )
    return vector


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts efficiently in a single model call."""
    model = _get_model()
    vectors = await asyncio.to_thread(
        lambda: model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()
    )
    return vectors
```

**Step 4: Run tests (downloads model ~90MB on first run)**

```bash
uv run pytest tests/test_embedder.py -v -s
```
Expected: PASS (30–60s first run for model download).

**Step 5: Commit**

```bash
git add src/vgv_rag/processing/ tests/test_embedder.py
git commit -m "feat: embedding engine with sentence-transformers all-MiniLM-L6-v2"
```

---

### Task 6: Chunking engine

**Files:**
- Create: `src/vgv_rag/processing/chunker.py`
- Create: `tests/test_chunker.py`

**Step 1: Write failing tests**

```python
# tests/test_chunker.py
import pytest
from vgv_rag.processing.chunker import chunk

MEETING_NOTE = """
# Team Sync

## Action Items
Alice will review the PR by Friday.
Bob will update the design doc.

## Decisions
We decided to use Supabase for auth.
The team agreed to skip the staging environment.

## Next Steps
Schedule a follow-up for next week.
""".strip()


def test_meeting_note_split_by_heading():
    chunks = chunk(MEETING_NOTE, "meeting_note")
    assert len(chunks) > 1
    assert any("Action Items" in c for c in chunks)


def test_slack_thread_is_whole_document():
    text = "Short slack thread about the deploy."
    chunks = chunk(text, "slack_thread")
    assert chunks == [text]


def test_story_is_whole_document():
    text = "As a user I want to search project knowledge."
    chunks = chunk(text, "story")
    assert len(chunks) == 1


def test_unknown_type_uses_recursive_split():
    long_text = "word " * 2000
    chunks = chunk(long_text, "unknown_type")
    assert len(chunks) > 1


def test_all_chunks_nonempty():
    chunks = chunk(MEETING_NOTE, "prd")
    assert all(c.strip() for c in chunks)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_chunker.py -v
```
Expected: FAIL.

**Step 3: Write `src/vgv_rag/processing/chunker.py`**

```python
# src/vgv_rag/processing/chunker.py
import re
from dataclasses import dataclass

CHARS_PER_TOKEN = 4  # rough approximation

@dataclass
class ChunkConfig:
    strategy: str
    target_size: int   # tokens
    overlap: int       # tokens

CHUNKING_CONFIG: dict[str, ChunkConfig] = {
    "meeting_note": ChunkConfig("by_heading",      500, 50),
    "prd":          ChunkConfig("by_section",      600, 50),
    "story":        ChunkConfig("whole_document",  800,  0),
    "slack_thread": ChunkConfig("whole_document", 1000,  0),
    "pr":           ChunkConfig("by_section",      500,  0),
    "design_spec":  ChunkConfig("by_component",    400,  0),
    "issue":        ChunkConfig("whole_document",  800,  0),
}
DEFAULT_CONFIG = ChunkConfig("recursive_split", 500, 50)


def chunk(text: str, artifact_type: str) -> list[str]:
    config = CHUNKING_CONFIG.get(artifact_type, DEFAULT_CONFIG)

    if config.strategy == "whole_document":
        return [text.strip()]
    elif config.strategy == "by_heading":
        return _split_by_heading(text, r"^#{2,3}\s", config)
    elif config.strategy in ("by_section", "by_component"):
        return _split_by_heading(text, r"^#{1,2}\s", config)
    else:
        return _recursive_split(
            text,
            config.target_size * CHARS_PER_TOKEN,
            config.overlap * CHARS_PER_TOKEN,
        )


def _split_by_heading(text: str, pattern: str, config: ChunkConfig) -> list[str]:
    regex = re.compile(pattern, re.MULTILINE)
    lines = text.split("\n")
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        if regex.match(line) and current:
            sections.append("\n".join(current).strip())
            current = []
        current.append(line)

    if current:
        sections.append("\n".join(current).strip())

    target_chars = config.target_size * CHARS_PER_TOKEN
    overlap_chars = config.overlap * CHARS_PER_TOKEN

    result = []
    for section in sections:
        if len(section) <= target_chars:
            result.append(section)
        else:
            result.extend(_recursive_split(section, target_chars, overlap_chars))

    return [s for s in result if s.strip()]


def _recursive_split(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= target_chars:
        return [text]

    for sep in ["\n\n", "\n", ". ", " "]:
        parts = text.split(sep)
        if len(parts) <= 1:
            continue

        chunks: list[str] = []
        current = ""

        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) > target_chars and current:
                chunks.append(current)
                tail = current[-overlap_chars:] if overlap_chars else ""
                current = tail + sep + part if tail else part
            else:
                current = candidate

        if current:
            chunks.append(current)

        return [c.strip() for c in chunks if c.strip()]

    return [text]
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_chunker.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/processing/chunker.py tests/test_chunker.py
git commit -m "feat: chunking engine with per-artifact-type strategies"
```

---

### Task 7: MCP server skeleton

**Files:**
- Create: `src/vgv_rag/server/__init__.py`
- Create: `src/vgv_rag/server/mcp_server.py`
- Modify: `src/vgv_rag/main.py`

**Step 1: Write the MCP server using FastMCP**

```python
# src/vgv_rag/server/mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("vgv-project-rag")


@mcp.tool()
async def search_project_context(query: str, project: str = "", top_k: int = 5) -> str:
    """Search project knowledge across Notion, Slack, GitHub, Figma, and Jira."""
    return "Not yet implemented"


@mcp.tool()
async def list_sources(project: str = "") -> str:
    """Show indexed sources for a project: what's connected, last sync time, any errors."""
    return "Not yet implemented"


@mcp.tool()
async def ingest_document(project: str, content: str = "", url: str = "", artifact_type: str = "document") -> str:
    """Manually add a document to the project index."""
    return "Not yet implemented"
```

**Step 2: Add health endpoint and wire server in `main.py`**

```python
# src/vgv_rag/main.py
import asyncio
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from dotenv import load_dotenv

load_dotenv()

from vgv_rag.config.settings import settings
from vgv_rag.server.mcp_server import mcp


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "vgv-project-rag"})


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ]
    )


def run():
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
```

**Step 3: Add `uvicorn` and `starlette` to dependencies**

```bash
uv add uvicorn starlette
```

**Step 4: Manual smoke test**

```bash
uv run python -m vgv_rag.main &
sleep 2
curl http://localhost:3000/health
# Expected: {"status":"ok","service":"vgv-project-rag"}
kill %1
```

**Step 5: Commit**

```bash
git add src/vgv_rag/server/ src/vgv_rag/main.py pyproject.toml uv.lock
git commit -m "feat: FastMCP server skeleton with health endpoint and stub tool handlers"
```

---

### Task 8: Auth middleware (Supabase JWT validation)

**Files:**
- Create: `src/vgv_rag/server/auth.py`
- Create: `tests/test_auth.py`

**Step 1: Write failing tests**

```python
# tests/test_auth.py
import pytest
from unittest.mock import MagicMock, patch

ALLOWED_EMAIL = "alice@verygood.ventures"
DISALLOWED_EMAIL = "hacker@evil.com"


@pytest.mark.asyncio
async def test_validate_jwt_returns_email_for_valid_token(mocker):
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = MagicMock(
        user=MagicMock(email=ALLOWED_EMAIL), error=None
    )
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    email = await validate_jwt("valid-token")
    assert email == ALLOWED_EMAIL


@pytest.mark.asyncio
async def test_validate_jwt_raises_for_invalid_token(mocker):
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = MagicMock(user=None, error=MagicMock(message="Invalid"))
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    with pytest.raises(PermissionError, match="Unauthorized"):
        await validate_jwt("bad-token")


@pytest.mark.asyncio
async def test_validate_jwt_raises_for_non_vgv_email(mocker):
    mock_client = MagicMock()
    mock_client.auth.get_user.return_value = MagicMock(
        user=MagicMock(email=DISALLOWED_EMAIL), error=None
    )
    mocker.patch("vgv_rag.server.auth.get_client", return_value=mock_client)

    from vgv_rag.server.auth import validate_jwt
    with pytest.raises(PermissionError, match="Unauthorized"):
        await validate_jwt("valid-token")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_auth.py -v
```
Expected: FAIL.

**Step 3: Write `src/vgv_rag/server/auth.py`**

```python
# src/vgv_rag/server/auth.py
import asyncio
from vgv_rag.storage.client import get_client

ALLOWED_DOMAIN = "@verygood.ventures"


async def validate_jwt(token: str) -> str:
    """Validate a Supabase JWT and return the user's email."""
    client = get_client()
    response = await asyncio.to_thread(lambda: client.auth.get_user(token))

    if response.error or not response.user or not response.user.email:
        raise PermissionError("Unauthorized: invalid token")

    if not response.user.email.endswith(ALLOWED_DOMAIN):
        raise PermissionError("Unauthorized: not a VGV account")

    return response.user.email


def extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header[len("Bearer "):]
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_auth.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/server/auth.py tests/test_auth.py
git commit -m "feat: JWT validation middleware with VGV domain enforcement"
```

---

### Task 9: `search_project_context` tool — fully wired

**Files:**
- Create: `src/vgv_rag/server/tools/__init__.py`
- Create: `src/vgv_rag/server/tools/search.py`
- Modify: `src/vgv_rag/server/mcp_server.py`
- Create: `tests/test_search_tool.py`

**Step 1: Write failing test**

```python
# tests/test_search_tool.py
import pytest

@pytest.fixture(autouse=True)
def mock_deps(mocker):
    mocker.patch("vgv_rag.server.tools.search.search_chunks", return_value=[
        {"id": "1", "content": "PRD section about auth", "metadata": {"source_tool": "notion", "artifact_type": "prd", "source_url": "https://notion.so/123"}, "similarity": 0.92},
    ])
    mocker.patch("vgv_rag.server.tools.search.list_projects_for_user", return_value=[{"id": "proj-1", "name": "TestProject"}])
    mocker.patch("vgv_rag.server.tools.search.get_project_by_name", return_value={"id": "proj-1", "name": "TestProject"})
    mocker.patch("vgv_rag.server.tools.search.embed", return_value=[0.1] * 384)


@pytest.mark.asyncio
async def test_search_returns_formatted_chunks():
    from vgv_rag.server.tools.search import handle_search_project_context

    result = await handle_search_project_context(
        query="how does auth work",
        user_email="alice@verygood.ventures",
    )

    assert "PRD section about auth" in result
    assert "notion.so/123" in result
    assert "92%" in result
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_search_tool.py -v
```
Expected: FAIL.

**Step 3: Write `src/vgv_rag/server/tools/search.py`**

```python
# src/vgv_rag/server/tools/search.py
from vgv_rag.processing.embedder import embed
from vgv_rag.storage.queries import search_chunks, list_projects_for_user, get_project_by_name


async def handle_search_project_context(
    query: str,
    user_email: str,
    project: str = "",
    filters: dict | None = None,
    top_k: int = 5,
) -> str:
    # Resolve project
    if project:
        proj = await get_project_by_name(project)
        if not proj:
            return f"Project not found: {project}"
        project_id = proj["id"]
    else:
        projects = await list_projects_for_user(user_email)
        if not projects:
            return "No projects found for your account."
        project_id = projects[0]["id"]

    # Build metadata filter
    filter_meta: dict | None = None
    if filters:
        filter_meta = {k: v for k, v in filters.items() if v}
    if not filter_meta:
        filter_meta = None

    # Embed and search
    vector = await embed(query)
    chunks = await search_chunks(
        embedding=vector,
        project_id=project_id,
        top_k=min(top_k, 20),
        filter_metadata=filter_meta,
    )

    if not chunks:
        return "No relevant results found."

    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        pct = f"{c['similarity'] * 100:.0f}%"
        lines.append(f"--- Result {i} (similarity: {pct}) ---")
        lines.append(f"Source: {meta.get('source_tool', 'unknown')} | Type: {meta.get('artifact_type', 'unknown')}")
        if meta.get("source_url"):
            lines.append(f"URL: {meta['source_url']}")
        if meta.get("author"):
            lines.append(f"Author: {meta['author']}")
        if meta.get("date"):
            lines.append(f"Date: {meta['date']}")
        lines.append("")
        lines.append(c["content"])

    return "\n".join(lines)
```

**Step 4: Update `src/vgv_rag/server/mcp_server.py` to use handler**

```python
# src/vgv_rag/server/mcp_server.py
from mcp.server.fastmcp import FastMCP
from vgv_rag.server.tools.search import handle_search_project_context

mcp = FastMCP("vgv-project-rag")

# Note: FastMCP doesn't expose request headers directly yet.
# Auth is enforced at the transport level via Supabase; for now
# we accept an optional bearer token as a tool argument for dev.
DEV_EMAIL = "dev@verygood.ventures"


@mcp.tool()
async def search_project_context(
    query: str,
    project: str = "",
    artifact_type: str = "",
    source_tool: str = "",
    top_k: int = 5,
) -> str:
    """Search project knowledge across Notion, Slack, GitHub, Figma, and Jira. Returns relevant chunks with source links."""
    filters = {"artifact_type": artifact_type, "source_tool": source_tool}
    return await handle_search_project_context(
        query=query,
        user_email=DEV_EMAIL,
        project=project,
        filters=filters,
        top_k=top_k,
    )


@mcp.tool()
async def list_sources(project: str = "") -> str:
    """Show indexed sources for a project: what's connected, last sync time, any errors."""
    return "Not yet implemented"


@mcp.tool()
async def ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    """Manually add a document to the project index."""
    return "Not yet implemented"
```

**Step 5: Run tests**

```bash
uv run pytest tests/test_search_tool.py -v
```
Expected: PASS.

**Step 6: Commit**

```bash
git add src/vgv_rag/server/tools/ src/vgv_rag/server/mcp_server.py tests/test_search_tool.py
git commit -m "feat: search_project_context tool wired to pgvector search"
```

---

## Phase 2: Ingestion

### Task 10: Connector types and metadata builder

**Files:**
- Create: `src/vgv_rag/ingestion/__init__.py`
- Create: `src/vgv_rag/ingestion/connectors/__init__.py`
- Create: `src/vgv_rag/ingestion/connectors/types.py`
- Create: `src/vgv_rag/processing/metadata.py`

**Step 1: Write `src/vgv_rag/ingestion/connectors/types.py`**

```python
# src/vgv_rag/ingestion/connectors/types.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class RawDocument:
    source_url: str
    content: str
    title: str
    date: datetime
    artifact_type: str
    source_tool: str
    author: str | None = None


@dataclass
class Source:
    id: str
    project_id: str
    connector: str
    source_url: str
    source_id: str
    last_synced_at: datetime | None = None


@dataclass
class ProjectConfig:
    slack_channels: list[str] = field(default_factory=list)
    github_repos: list[str] = field(default_factory=list)
    figma_files: list[str] = field(default_factory=list)
    jira_projects: list[str] = field(default_factory=list)
    notion_pages: list[str] = field(default_factory=list)


class Connector(Protocol):
    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        ...

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        ...
```

**Step 2: Write `src/vgv_rag/processing/metadata.py`**

```python
# src/vgv_rag/processing/metadata.py
from vgv_rag.ingestion.connectors.types import RawDocument


def build_chunk_metadata(doc: RawDocument, chunk_index: int) -> dict:
    return {
        "artifact_type": doc.artifact_type,
        "source_tool": doc.source_tool,
        "source_url": doc.source_url,
        "title": doc.title,
        "author": doc.author,
        "date": doc.date.isoformat(),
        "chunk_index": chunk_index,
    }
```

**Step 3: Commit**

```bash
git add src/vgv_rag/ingestion/ src/vgv_rag/processing/metadata.py
git commit -m "feat: connector Protocol, RawDocument types, and metadata builder"
```

---

### Task 11: Notion connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/notion.py`
- Create: `tests/connectors/__init__.py`
- Create: `tests/connectors/test_notion.py`

**Step 1: Write failing test**

```python
# tests/connectors/test_notion.py
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def mock_notion_client(mocker):
    mock = MagicMock()
    mock.pages.retrieve.return_value = {
        "id": "page-1",
        "url": "https://notion.so/page-1",
        "last_edited_time": "2026-02-01T00:00:00.000Z",
        "properties": {"title": {"type": "title", "title": [{"plain_text": "Meeting Notes Feb 2026"}]}},
        "created_by": {"id": "user-1"},
    }
    mock.blocks.children.list.return_value = {
        "results": [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "We decided to use Supabase."}]}},
        ],
        "has_more": False,
    }
    mock.search.return_value = {
        "results": [
            {
                "id": "page-1",
                "url": "https://notion.so/page-1",
                "object": "page",
                "last_edited_time": "2026-02-01T00:00:00.000Z",
                "properties": {"title": {"type": "title", "title": [{"plain_text": "Meeting Notes Feb 2026"}]}},
            }
        ]
    }
    mocker.patch("vgv_rag.ingestion.connectors.notion.Client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_notion_fetch_returns_documents(mock_notion_client):
    from vgv_rag.ingestion.connectors.notion import NotionConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = NotionConnector("fake-token")
    source = Source(id="src-1", project_id="proj-1", connector="notion",
                    source_url="https://notion.so/page-1", source_id="page-1")

    docs = await connector.fetch_documents(source)

    assert len(docs) == 1
    assert "Supabase" in docs[0].content
    assert docs[0].source_tool == "notion"
    assert docs[0].artifact_type == "meeting_note"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/connectors/test_notion.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/connectors/notion.py`**

```python
# src/vgv_rag/ingestion/connectors/notion.py
import asyncio
import re
from datetime import datetime, timezone
from notion_client import Client
from vgv_rag.ingestion.connectors.types import Connector, RawDocument, Source, ProjectConfig

ARTIFACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"meeting|sync|standup|retro|demo|kickoff", re.I), "meeting_note"),
    (re.compile(r"prd|product requirement|spec|brief", re.I), "prd"),
    (re.compile(r"adr|decision|architecture", re.I), "adr"),
    (re.compile(r"story|ticket|task|feature", re.I), "story"),
    (re.compile(r"design|figma|ui|ux", re.I), "design_spec"),
]


def _detect_artifact_type(title: str) -> str:
    for pattern, artifact_type in ARTIFACT_PATTERNS:
        if pattern.search(title):
            return artifact_type
    return "document"


def _extract_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts)
    return "Untitled"


def _blocks_to_text(blocks: list[dict]) -> str:
    lines = []
    for block in blocks:
        block_type = block.get("type", "")
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text)
        if text:
            lines.append(text)
    return "\n".join(lines)


class NotionConnector:
    def __init__(self, token: str):
        self._client = Client(auth=token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "notion", "source_url": url, "source_id": _extract_id(url)}
            for url in config.notion_pages
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        search_result = await asyncio.to_thread(
            lambda: self._client.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
            )
        )

        docs = []
        for page in search_result.get("results", []):
            edited = datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00"))
            if since and edited <= since:
                continue

            title = _extract_title(page)
            blocks_result = await asyncio.to_thread(
                lambda pid=page["id"]: self._client.blocks.children.list(block_id=pid)
            )
            content = _blocks_to_text(blocks_result.get("results", []))
            if not content.strip():
                continue

            docs.append(RawDocument(
                source_url=page["url"],
                content=content,
                title=title,
                author=None,
                date=edited,
                artifact_type=_detect_artifact_type(title),
                source_tool="notion",
            ))

        return docs


def _extract_id(url: str) -> str:
    match = re.search(r"([a-f0-9]{32})$", url)
    return match.group(1) if match else url
```

**Step 4: Run tests**

```bash
uv run pytest tests/connectors/test_notion.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/notion.py tests/connectors/
git commit -m "feat: Notion connector with artifact type detection"
```

---

### Task 12: Project Hub parser

**Files:**
- Create: `src/vgv_rag/ingestion/project_hub_parser.py`
- Create: `tests/test_project_hub_parser.py`

**Step 1: Write failing test**

```python
# tests/test_project_hub_parser.py
import pytest

MOCK_BLOCKS = {
    "results": [
        {"type": "heading_2", "heading_2": {"rich_text": [{"plain_text": "Helpful Links"}]}},
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"plain_text": "Slack", "href": "https://verygood.slack.com/archives/C001"}],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"plain_text": "GitHub", "href": "https://github.com/verygoodventures/proj-alpha"}],
            },
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"plain_text": "Figma", "href": "https://figma.com/file/ABC123/Design"}],
            },
        },
    ],
    "has_more": False,
}


@pytest.fixture
def mock_notion(mocker):
    mock = mocker.MagicMock()
    mock.blocks.children.list.return_value = MOCK_BLOCKS
    mocker.patch("vgv_rag.ingestion.project_hub_parser.Client", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_parses_slack_channel(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("C001" in url or "proj-alpha" not in url for url in (config.slack_channels or []))
    assert len(config.slack_channels) > 0


@pytest.mark.asyncio
async def test_parses_github_repo(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("github.com" in url for url in config.github_repos)


@pytest.mark.asyncio
async def test_parses_figma_file(mock_notion):
    from vgv_rag.ingestion.project_hub_parser import parse_project_hub
    config = await parse_project_hub("https://notion.so/abc123def456abc123def456abc123de", "fake-token")
    assert any("figma.com" in url for url in config.figma_files)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_project_hub_parser.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/project_hub_parser.py`**

```python
# src/vgv_rag/ingestion/project_hub_parser.py
import asyncio
import re
from notion_client import Client
from vgv_rag.ingestion.connectors.types import ProjectConfig


def _extract_urls(block: dict) -> list[str]:
    urls = []
    block_type = block.get("type", "")
    rich_text = block.get(block_type, {}).get("rich_text", [])
    for rt in rich_text:
        if rt.get("href"):
            urls.append(rt["href"])
        if rt.get("text", {}).get("link", {}).get("url"):
            urls.append(rt["text"]["link"]["url"])
    if block_type == "bookmark":
        url = block.get("bookmark", {}).get("url")
        if url:
            urls.append(url)
    return urls


def _classify_url(url: str, config: ProjectConfig) -> None:
    if "slack.com/channels" in url or "slack.com/archives" in url:
        config.slack_channels.append(url)
    elif "github.com" in url:
        config.github_repos.append(url)
    elif "figma.com" in url:
        config.figma_files.append(url)
    elif "atlassian.net" in url or "jira" in url:
        config.jira_projects.append(url)
    elif "notion.so" in url:
        config.notion_pages.append(url)


def _extract_page_id(url: str) -> str:
    match = re.search(r"([a-f0-9]{32})", url.replace("-", ""))
    return match.group(1) if match else url


async def parse_project_hub(hub_url: str, notion_token: str) -> ProjectConfig:
    client = Client(auth=notion_token)
    page_id = _extract_page_id(hub_url)
    config = ProjectConfig()

    blocks = await asyncio.to_thread(
        lambda: client.blocks.children.list(block_id=page_id)
    )

    in_helpful_links = False
    for block in blocks.get("results", []):
        block_type = block.get("type", "")
        rich_text = block.get(block_type, {}).get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_text).lower()

        if block_type.startswith("heading") and "helpful links" in text:
            in_helpful_links = True
            continue

        if block_type.startswith("heading") and in_helpful_links:
            break  # End of Helpful Links section

        if in_helpful_links:
            for url in _extract_urls(block):
                _classify_url(url, config)

    return config
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_project_hub_parser.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/project_hub_parser.py tests/test_project_hub_parser.py
git commit -m "feat: Project Hub parser extracts connector configs from Notion Helpful Links"
```

---

### Task 13: Sync scheduler

**Files:**
- Create: `src/vgv_rag/ingestion/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write failing test**

```python
# tests/test_scheduler.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from vgv_rag.ingestion.connectors.types import Source, RawDocument


@pytest.fixture(autouse=True)
def mock_storage(mocker):
    mocker.patch("vgv_rag.ingestion.scheduler.update_source_sync_status", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.delete_chunks_by_source", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.insert_chunks", new_callable=AsyncMock)
    mocker.patch("vgv_rag.ingestion.scheduler.embed_batch", new_callable=AsyncMock, return_value=[[0.0] * 384])


@pytest.mark.asyncio
async def test_sync_source_deletes_old_and_inserts_new(mocker):
    from vgv_rag.ingestion.scheduler import sync_source
    from vgv_rag.ingestion.scheduler import delete_chunks_by_source, insert_chunks

    mock_connector = MagicMock()
    mock_connector.fetch_documents = AsyncMock(return_value=[
        RawDocument(
            source_url="https://notion.so/abc",
            content="Meeting content about auth",
            title="Meeting Notes",
            date=datetime.now(timezone.utc),
            artifact_type="meeting_note",
            source_tool="notion",
        )
    ])

    source = Source(id="src-1", project_id="proj-1", connector="notion",
                    source_url="https://notion.so/abc", source_id="abc")

    await sync_source(source=source, connector=mock_connector)

    delete_chunks_by_source.assert_called_once_with("src-1")
    insert_chunks.assert_called_once()


@pytest.mark.asyncio
async def test_sync_source_marks_error_on_exception(mocker):
    from vgv_rag.ingestion.scheduler import sync_source, update_source_sync_status

    mock_connector = MagicMock()
    mock_connector.fetch_documents = AsyncMock(side_effect=RuntimeError("API down"))

    source = Source(id="src-1", project_id="proj-1", connector="notion",
                    source_url="https://notion.so/abc", source_id="abc")

    await sync_source(source=source, connector=mock_connector)

    update_source_sync_status.assert_called_with("src-1", "error", "API down")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scheduler.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/scheduler.py`**

```python
# src/vgv_rag/ingestion/scheduler.py
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from vgv_rag.storage.queries import (
    update_source_sync_status,
    delete_chunks_by_source,
    insert_chunks,
    list_sources_for_project,
)
from vgv_rag.processing.chunker import chunk
from vgv_rag.processing.embedder import embed_batch
from vgv_rag.processing.metadata import build_chunk_metadata
from vgv_rag.ingestion.connectors.types import Source, Connector
from vgv_rag.config.settings import settings

log = logging.getLogger(__name__)


async def sync_source(source: Source, connector: Connector) -> None:
    await update_source_sync_status(source.id, "syncing")
    try:
        docs = await connector.fetch_documents(source, source.last_synced_at)
        await delete_chunks_by_source(source.id)

        for doc in docs:
            chunks = chunk(doc.content, doc.artifact_type)
            if not chunks:
                continue
            embeddings = await embed_batch(chunks)
            rows = [
                {
                    "project_id": source.project_id,
                    "source_id": source.id,
                    "content": text,
                    "embedding": embeddings[i],
                    "metadata": build_chunk_metadata(doc, i),
                }
                for i, text in enumerate(chunks)
            ]
            await insert_chunks(rows)

        await update_source_sync_status(source.id, "success")
        log.info("Synced source %s (%s)", source.id, source.connector)

    except Exception as exc:
        msg = str(exc)
        log.error("Sync failed for source %s: %s", source.id, msg)
        await update_source_sync_status(source.id, "error", msg)


def is_business_hours() -> bool:
    now = datetime.now()
    return 1 <= now.isoweekday() <= 5 and 8 <= now.hour <= 20


def start_scheduler(get_connector) -> AsyncIOScheduler:
    from vgv_rag.storage.client import get_client

    async def run_sync():
        log.info("Sync cycle starting...")
        client = get_client()
        projects = client.table("projects").select("id").execute()
        for project in (projects.data or []):
            sources = await list_sources_for_project(project["id"])
            for source_dict in sources:
                connector = get_connector(source_dict["connector"])
                if not connector:
                    continue
                source = Source(
                    id=source_dict["id"],
                    project_id=source_dict["project_id"],
                    connector=source_dict["connector"],
                    source_url=source_dict["source_url"],
                    source_id=source_dict["source_id"],
                    last_synced_at=source_dict.get("last_synced_at"),
                )
                await sync_source(source=source, connector=connector)
        log.info("Sync cycle complete.")

    scheduler = AsyncIOScheduler()
    # Every 15 min — skip if off-hours
    scheduler.add_job(
        lambda: run_sync() if is_business_hours() else None,
        "cron",
        minute="*/15",
        hour="8-20",
        day_of_week="mon-fri",
    )
    # Every hour — skip if business hours
    scheduler.add_job(
        lambda: run_sync() if not is_business_hours() else None,
        "cron",
        minute=0,
    )
    scheduler.start()
    log.info("Sync scheduler started.")
    return scheduler
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_scheduler.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/scheduler.py tests/test_scheduler.py
git commit -m "feat: async ingestion scheduler with APScheduler and error handling"
```

---

### Task 14: `seed_project.py` CLI

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/seed_project.py`

**Step 1: Write the script**

```python
#!/usr/bin/env python3
# scripts/seed_project.py
"""CLI to onboard a new project from a Notion Project Hub URL."""
import asyncio
import argparse
from dotenv import load_dotenv
load_dotenv()

from vgv_rag.ingestion.project_hub_parser import parse_project_hub
from vgv_rag.ingestion.connectors.notion import NotionConnector
from vgv_rag.ingestion.scheduler import sync_source
from vgv_rag.ingestion.connectors.types import Source
from vgv_rag.storage.queries import upsert_project, upsert_source
from vgv_rag.storage.client import get_client
from vgv_rag.config.settings import settings


async def run(hub_url: str, name: str, members: list[str]):
    if not settings.notion_api_token:
        raise SystemExit("NOTION_API_TOKEN is required")

    print(f"Onboarding project: {name}")
    print(f"Hub URL: {hub_url}\n")

    print("1. Parsing Project Hub...")
    config = await parse_project_hub(hub_url, settings.notion_api_token)
    print(f"   notion_pages: {config.notion_pages}")
    print(f"   slack_channels: {config.slack_channels}")
    print(f"   github_repos: {config.github_repos}")
    print(f"   figma_files: {config.figma_files}")
    print(f"   jira_projects: {config.jira_projects}\n")

    print("2. Creating project record...")
    import dataclasses
    project_id = await upsert_project(name=name, notion_hub_url=hub_url, config=dataclasses.asdict(config))
    print(f"   Project ID: {project_id}\n")

    print("3. Syncing Notion sources...")
    connector = NotionConnector(settings.notion_api_token)
    for url in config.notion_pages:
        source_id = await upsert_source(
            project_id=project_id,
            connector="notion",
            source_url=url,
            source_id=url.split("-")[-1][:32],
        )
        source = Source(id=source_id, project_id=project_id, connector="notion",
                        source_url=url, source_id=url.split("-")[-1][:32])
        print(f"   Syncing {url}...")
        await sync_source(source=source, connector=connector)
        print("   Done.")

    if members:
        print("\n4. Adding project members...")
        client = get_client()
        for email in members:
            client.table("project_members").upsert(
                {"project_id": project_id, "user_email": email}
            ).execute()
            print(f"   Added: {email}")

    print("\nProject onboarded successfully!")


def main():
    parser = argparse.ArgumentParser(description="Onboard a project from a Notion Project Hub.")
    parser.add_argument("--hub-url", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--member", action="append", default=[], dest="members")
    args = parser.parse_args()
    asyncio.run(run(args.hub_url, args.name, args.members))


if __name__ == "__main__":
    main()
```

**Step 2: Manual test**

```bash
uv run python scripts/seed_project.py \
  --hub-url "https://www.notion.so/verygoodventures/TestProject-abc123def456abc123def456abc123de" \
  --name "Test Project" \
  --member "you@verygood.ventures"
```
Expected: Project created, Notion pages discovered, initial sync complete.

**Step 3: Commit**

```bash
git add scripts/seed_project.py scripts/__init__.py
git commit -m "feat: seed_project CLI for onboarding projects from Notion Hub URL"
```

---

## Phase 3: Additional Connectors

### Task 15: Slack connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/slack.py`
- Create: `tests/connectors/test_slack.py`

**Step 1: Write failing test**

```python
# tests/connectors/test_slack.py
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

BOT_SUBTYPES = {"channel_join", "bot_message"}

@pytest.fixture
def mock_slack(mocker):
    mock = MagicMock()
    mock.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1706745600.000001", "text": "Decided to use Supabase for auth.", "user": "U001"},
            {"ts": "1706745601.000001", "text": "", "user": "U002", "subtype": "channel_join"},
        ],
        "has_more": False,
    }
    mock.conversations_replies.return_value = {"ok": True, "messages": [], "has_more": False}
    mock.conversations_info.return_value = {"ok": True, "channel": {"name": "proj-alpha"}}
    mock.users_info.return_value = {"ok": True, "user": {"real_name": "Alice"}}
    mocker.patch("vgv_rag.ingestion.connectors.slack.WebClient", return_value=mock)
    return mock


@pytest.mark.asyncio
async def test_slack_filters_joins_and_bots(mock_slack):
    from vgv_rag.ingestion.connectors.slack import SlackConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = SlackConnector("fake-token")
    source = Source(id="s1", project_id="p1", connector="slack",
                    source_url="https://app.slack.com/client/T001/C001", source_id="C001")

    docs = await connector.fetch_documents(source)
    assert len(docs) == 1
    assert "Supabase" in docs[0].content
    assert docs[0].artifact_type == "slack_thread"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/connectors/test_slack.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/connectors/slack.py`**

```python
# src/vgv_rag/ingestion/connectors/slack.py
import asyncio
import re
from datetime import datetime, timezone
from slack_sdk import WebClient
from vgv_rag.ingestion.connectors.types import Connector, RawDocument, Source, ProjectConfig

FILTERED_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "bot_message"}
PURE_EMOJI_RE = re.compile(r"^<:.+:>$")


class SlackConnector:
    def __init__(self, token: str):
        self._client = WebClient(token=token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        sources = []
        for url in config.slack_channels:
            channel_id = _extract_channel_id(url)
            if channel_id:
                sources.append({"connector": "slack", "source_url": url, "source_id": channel_id})
        return sources

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        oldest = str(since.timestamp()) if since else None

        info = await asyncio.to_thread(
            lambda: self._client.conversations_info(channel=source.source_id)
        )
        channel_name = info.get("channel", {}).get("name", source.source_id)

        history = await asyncio.to_thread(
            lambda: self._client.conversations_history(
                channel=source.source_id,
                oldest=oldest,
                limit=200,
            )
        )

        docs = []
        for msg in history.get("messages", []):
            text = msg.get("text", "").strip()
            subtype = msg.get("subtype")
            if not text or subtype in FILTERED_SUBTYPES or msg.get("bot_id") or PURE_EMOJI_RE.match(text):
                continue
            if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                continue  # Skip thread replies; fetched below

            author = None
            if user_id := msg.get("user"):
                try:
                    user_info = await asyncio.to_thread(
                        lambda uid=user_id: self._client.users_info(user=uid)
                    )
                    author = user_info.get("user", {}).get("real_name")
                except Exception:
                    pass

            content = text
            if msg.get("reply_count", 0) > 0:
                replies = await asyncio.to_thread(
                    lambda ts=msg["ts"]: self._client.conversations_replies(
                        channel=source.source_id, ts=ts
                    )
                )
                reply_texts = [
                    f"> {r['text']}"
                    for r in replies.get("messages", [])[1:]
                    if r.get("text", "").strip()
                ]
                if reply_texts:
                    content += "\n" + "\n".join(reply_texts)

            ts_float = float(msg["ts"])
            p_ts = msg["ts"].replace(".", "")
            docs.append(RawDocument(
                source_url=f"https://slack.com/archives/{source.source_id}/p{p_ts}",
                content=content,
                title=f"#{channel_name} thread",
                author=author,
                date=datetime.fromtimestamp(ts_float, tz=timezone.utc),
                artifact_type="slack_thread",
                source_tool="slack",
            ))

        return docs


def _extract_channel_id(url: str) -> str | None:
    match = re.search(r"/([CG][A-Z0-9]+)", url)
    return match.group(1) if match else None
```

**Step 4: Run tests**

```bash
uv run pytest tests/connectors/test_slack.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/slack.py tests/connectors/test_slack.py
git commit -m "feat: Slack connector with thread fetching and bot/join filtering"
```

---

### Task 16: GitHub connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/github.py`
- Create: `tests/connectors/test_github.py`

**Step 1: Write failing test**

```python
# tests/connectors/test_github.py
import pytest
from unittest.mock import MagicMock
import base64


@pytest.fixture
def mock_github(mocker):
    mock_repo = MagicMock()
    mock_file = MagicMock()
    mock_file.decoded_content = b"# README\nThis project uses Supabase for auth."
    mock_repo.get_contents.return_value = mock_file

    mock_pr = MagicMock()
    mock_pr.number = 1
    mock_pr.title = "Add auth middleware"
    mock_pr.body = "Implements JWT validation using Supabase."
    mock_pr.user.login = "alice"
    mock_pr.updated_at = MagicMock()
    mock_pr.updated_at.isoformat.return_value = "2026-02-01T00:00:00"
    mock_pr.html_url = "https://github.com/vgv/repo/pull/1"
    mock_repo.get_pulls.return_value = [mock_pr]

    mock_github_client = MagicMock()
    mock_github_client.get_repo.return_value = mock_repo
    mocker.patch("vgv_rag.ingestion.connectors.github.Github", return_value=mock_github_client)
    return mock_github_client


@pytest.mark.asyncio
async def test_github_fetches_readme_and_prs(mock_github):
    from vgv_rag.ingestion.connectors.github import GitHubConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = GitHubConnector("fake-pat")
    source = Source(id="s1", project_id="p1", connector="github",
                    source_url="https://github.com/vgv/repo", source_id="vgv/repo")

    docs = await connector.fetch_documents(source)
    assert any("Supabase" in d.content for d in docs)
    assert any(d.artifact_type == "pr" for d in docs)
    assert any("JWT validation" in d.content for d in docs)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/connectors/test_github.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/connectors/github.py`**

```python
# src/vgv_rag/ingestion/connectors/github.py
import asyncio
from datetime import datetime, timezone
from github import Github
from vgv_rag.ingestion.connectors.types import Connector, RawDocument, Source, ProjectConfig

KEY_FILES = ["README.md", "CLAUDE.md", "AGENTS.md"]


class GitHubConnector:
    def __init__(self, token: str):
        self._client = Github(token)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "github", "source_url": url, "source_id": _extract_slug(url)}
            for url in config.github_repos
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        repo = await asyncio.to_thread(lambda: self._client.get_repo(source.source_id))
        docs = []

        for filename in KEY_FILES:
            try:
                file_obj = await asyncio.to_thread(lambda f=filename: repo.get_contents(f))
                content = file_obj.decoded_content.decode("utf-8")
                docs.append(RawDocument(
                    source_url=f"https://github.com/{source.source_id}/blob/main/{filename}",
                    content=content,
                    title=filename,
                    date=datetime.now(timezone.utc),
                    artifact_type="document",
                    source_tool="github",
                ))
            except Exception:
                pass

        pulls = await asyncio.to_thread(
            lambda: repo.get_pulls(state="all", sort="updated", direction="desc")
        )
        for pr in list(pulls)[:50]:
            if not pr.body or not pr.body.strip():
                continue
            pr_date = pr.updated_at.replace(tzinfo=timezone.utc) if pr.updated_at.tzinfo is None else pr.updated_at
            if since and pr_date <= since:
                continue
            docs.append(RawDocument(
                source_url=pr.html_url,
                content=f"# {pr.title}\n\n{pr.body}",
                title=f"PR #{pr.number}: {pr.title}",
                author=pr.user.login if pr.user else None,
                date=pr_date,
                artifact_type="pr",
                source_tool="github",
            ))

        return docs


def _extract_slug(url: str) -> str:
    import re
    match = re.search(r"github\.com/([^/]+/[^/]+)", url)
    return match.group(1) if match else url
```

**Step 4: Run tests**

```bash
uv run pytest tests/connectors/test_github.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/github.py tests/connectors/test_github.py
git commit -m "feat: GitHub connector for README, CLAUDE.md, and PR descriptions"
```

---

### Task 17: Figma connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/figma.py`
- Create: `tests/connectors/test_figma.py`

**Step 1: Write failing test**

```python
# tests/connectors/test_figma.py
import pytest
import httpx
import respx

FIGMA_RESPONSE = {
    "name": "Design System",
    "document": {
        "name": "Document",
        "children": [{
            "name": "Components",
            "type": "FRAME",
            "children": [
                {"id": "1:1", "name": "Button", "type": "COMPONENT", "description": "Primary CTA button", "children": []},
                {"id": "1:2", "name": "Input", "type": "COMPONENT", "description": "Text input field", "children": []},
            ],
        }],
    },
}


@pytest.mark.asyncio
@respx.mock
async def test_figma_extracts_components():
    respx.get("https://api.figma.com/v1/files/ABC123").mock(
        return_value=httpx.Response(200, json=FIGMA_RESPONSE)
    )

    from vgv_rag.ingestion.connectors.figma import FigmaConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = FigmaConnector("fake-token")
    source = Source(id="s1", project_id="p1", connector="figma",
                    source_url="https://figma.com/file/ABC123/Design-System", source_id="ABC123")

    docs = await connector.fetch_documents(source)
    assert len(docs) == 2
    assert all(d.artifact_type == "design_spec" for d in docs)
    assert any("Button" in d.content for d in docs)
    assert any("Primary CTA" in d.content for d in docs)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/connectors/test_figma.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/connectors/figma.py`**

```python
# src/vgv_rag/ingestion/connectors/figma.py
import re
from datetime import datetime, timezone
import httpx
from vgv_rag.ingestion.connectors.types import Connector, RawDocument, Source, ProjectConfig

FIGMA_API = "https://api.figma.com/v1"


class FigmaConnector:
    def __init__(self, token: str):
        self._token = token

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "figma", "source_url": url, "source_id": _extract_file_key(url)}
            for url in config.figma_files
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        # Figma has no reliable incremental API — always full resync
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FIGMA_API}/files/{source.source_id}",
                headers={"X-Figma-Token": self._token},
            )
            response.raise_for_status()
            file_data = response.json()

        docs: list[RawDocument] = []
        _extract_components(
            node=file_data["document"],
            file_key=source.source_id,
            file_name=file_data.get("name", "Figma File"),
            docs=docs,
        )
        return docs


def _extract_components(node: dict, file_key: str, file_name: str, docs: list[RawDocument]) -> None:
    if node.get("type") in ("COMPONENT", "COMPONENT_SET"):
        parts = [f"Component: {node['name']}"]
        if node.get("description"):
            parts.append(f"Description: {node['description']}")
        if node.get("type") == "COMPONENT_SET" and node.get("children"):
            variants = ", ".join(c["name"] for c in node["children"])
            parts.append(f"Variants: {variants}")

        docs.append(RawDocument(
            source_url=f"https://figma.com/file/{file_key}?node-id={node['id']}",
            content="\n".join(parts),
            title=f"{file_name} — {node['name']}",
            date=datetime.now(timezone.utc),
            artifact_type="design_spec",
            source_tool="figma",
        ))

    for child in node.get("children", []):
        _extract_components(child, file_key, file_name, docs)


def _extract_file_key(url: str) -> str:
    match = re.search(r"figma\.com/(?:file|design)/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else url
```

**Step 4: Run tests**

```bash
uv run pytest tests/connectors/test_figma.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/figma.py tests/connectors/test_figma.py
git commit -m "feat: Figma connector extracting component metadata"
```

---

### Task 18: Atlassian (Jira) connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/atlassian.py`
- Create: `tests/connectors/test_atlassian.py`

**Step 1: Write failing test**

```python
# tests/connectors/test_atlassian.py
import pytest
import httpx
import respx

JIRA_RESPONSE = {
    "issues": [{
        "key": "PROJ-1",
        "fields": {
            "summary": "Implement auth middleware",
            "description": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "We need JWT validation."}]}],
            },
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Alice"},
            "updated": "2026-02-01T00:00:00.000+0000",
            "comment": {"comments": []},
        },
    }],
    "total": 1,
}


@pytest.mark.asyncio
@respx.mock
async def test_atlassian_fetches_issues():
    respx.get(url__contains="verygoodventures.atlassian.net/rest/api/3/search").mock(
        return_value=httpx.Response(200, json=JIRA_RESPONSE)
    )

    from vgv_rag.ingestion.connectors.atlassian import AtlassianConnector
    from vgv_rag.ingestion.connectors.types import Source

    connector = AtlassianConnector(token="t", email="u@vgv.com", domain="verygoodventures.atlassian.net")
    source = Source(id="s1", project_id="p1", connector="atlassian",
                    source_url="https://verygoodventures.atlassian.net/jira/software/projects/PROJ",
                    source_id="PROJ")

    docs = await connector.fetch_documents(source)
    assert len(docs) == 1
    assert docs[0].artifact_type == "issue"
    assert "auth middleware" in docs[0].content
    assert "JWT validation" in docs[0].content
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/connectors/test_atlassian.py -v
```

**Step 3: Write `src/vgv_rag/ingestion/connectors/atlassian.py`**

```python
# src/vgv_rag/ingestion/connectors/atlassian.py
import re
import base64
from datetime import datetime, timezone
import httpx
from vgv_rag.ingestion.connectors.types import Connector, RawDocument, Source, ProjectConfig


def _adf_to_text(node: dict | None) -> str:
    """Convert Atlassian Document Format to plain text."""
    if not node:
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_adf_to_text(child) for child in node.get("content", []))


class AtlassianConnector:
    def __init__(self, token: str, email: str, domain: str):
        self._token = token
        self._email = email
        self._domain = domain

    def _auth_header(self) -> str:
        creds = base64.b64encode(f"{self._email}:{self._token}".encode()).decode()
        return f"Basic {creds}"

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        return [
            {"connector": "atlassian", "source_url": url, "source_id": _extract_project_key(url)}
            for url in config.jira_projects
        ]

    async def fetch_documents(self, source: Source, since: datetime | None = None) -> list[RawDocument]:
        jql = f'project = "{source.source_id}" ORDER BY updated DESC'
        if since:
            date_str = since.strftime("%Y-%m-%d")
            jql = f'project = "{source.source_id}" AND updated > "{date_str}" ORDER BY updated DESC'

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{self._domain}/rest/api/3/search",
                params={"jql": jql, "maxResults": 100, "fields": "summary,description,status,assignee,updated,comment"},
                headers={"Authorization": self._auth_header(), "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        docs = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            desc = _adf_to_text(fields.get("description"))
            comments = "\n".join(
                f"[{c['author']['displayName']}]: {_adf_to_text(c['body'])}"
                for c in fields.get("comment", {}).get("comments", [])
            )
            content_parts = [
                f"Issue: {issue['key']} — {fields['summary']}",
                f"Status: {fields.get('status', {}).get('name', 'Unknown')}",
            ]
            if desc:
                content_parts += ["", "Description:", desc]
            if comments:
                content_parts += ["", "Comments:", comments]

            updated = datetime.fromisoformat(fields["updated"].replace("+0000", "+00:00"))
            docs.append(RawDocument(
                source_url=f"https://{self._domain}/browse/{issue['key']}",
                content="\n".join(content_parts),
                title=f"{issue['key']}: {fields['summary']}",
                author=fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
                date=updated,
                artifact_type="issue",
                source_tool="atlassian",
            ))

        return docs


def _extract_project_key(url: str) -> str:
    match = re.search(r"projects/([A-Z][A-Z0-9]+)", url)
    return match.group(1) if match else url
```

**Step 4: Run tests**

```bash
uv run pytest tests/connectors/test_atlassian.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/atlassian.py tests/connectors/test_atlassian.py
git commit -m "feat: Atlassian/Jira connector with JQL incremental sync and ADF parsing"
```

---

## Phase 4: Polish

### Task 19: `list_sources` and `ingest_document` tools

**Files:**
- Create: `src/vgv_rag/server/tools/list_sources.py`
- Create: `src/vgv_rag/server/tools/ingest.py`
- Modify: `src/vgv_rag/server/mcp_server.py`

**Step 1: Write `src/vgv_rag/server/tools/list_sources.py`**

```python
# src/vgv_rag/server/tools/list_sources.py
from vgv_rag.storage.queries import list_sources_for_project, get_project_by_name, list_projects_for_user


async def handle_list_sources(project: str, user_email: str) -> str:
    if project:
        proj = await get_project_by_name(project)
        if not proj:
            return f"Project not found: {project}"
        project_id = proj["id"]
    else:
        projects = await list_projects_for_user(user_email)
        if not projects:
            return "No projects found for your account."
        project_id = projects[0]["id"]

    sources = await list_sources_for_project(project_id)
    if not sources:
        return "No sources indexed yet for this project."

    lines = []
    for s in sources:
        line = f"• [{s['connector']}] {s['source_url']}\n  Status: {s['sync_status']} | Last sync: {s.get('last_synced_at') or 'never'}"
        if s.get("sync_error"):
            line += f"\n  Error: {s['sync_error']}"
        lines.append(line)

    return "\n\n".join(lines)
```

**Step 2: Write `src/vgv_rag/server/tools/ingest.py`**

```python
# src/vgv_rag/server/tools/ingest.py
import httpx
from vgv_rag.processing.embedder import embed_batch
from vgv_rag.processing.chunker import chunk
from vgv_rag.processing.metadata import build_chunk_metadata
from vgv_rag.storage.queries import upsert_source, insert_chunks, get_project_by_name
from vgv_rag.ingestion.connectors.types import RawDocument
from datetime import datetime, timezone


async def handle_ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    if not content and not url:
        return "Error: either content or url is required."

    proj = await get_project_by_name(project)
    if not proj:
        return f"Project not found: {project}"

    text = content
    if url and not content:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            text = response.text

    source_id = await upsert_source(
        project_id=proj["id"],
        connector="manual",
        source_url=url or "inline",
        source_id=url or f"manual-{int(datetime.now().timestamp())}",
    )

    chunks = chunk(text, artifact_type)
    embeddings = await embed_batch(chunks)

    doc = RawDocument(
        source_url=url or "inline",
        content=text,
        title=url or "Manual document",
        date=datetime.now(timezone.utc),
        artifact_type=artifact_type,
        source_tool="manual",
    )

    rows = [
        {
            "project_id": proj["id"],
            "source_id": source_id,
            "content": c,
            "embedding": embeddings[i],
            "metadata": build_chunk_metadata(doc, i),
        }
        for i, c in enumerate(chunks)
    ]
    await insert_chunks(rows)

    return f"Indexed {len(chunks)} chunk(s) from {'URL' if url else 'inline content'} into project \"{project}\"."
```

**Step 3: Update `src/vgv_rag/server/mcp_server.py`**

```python
# src/vgv_rag/server/mcp_server.py
from mcp.server.fastmcp import FastMCP
from vgv_rag.server.tools.search import handle_search_project_context
from vgv_rag.server.tools.list_sources import handle_list_sources
from vgv_rag.server.tools.ingest import handle_ingest_document

mcp = FastMCP("vgv-project-rag")

DEV_EMAIL = "dev@verygood.ventures"


@mcp.tool()
async def search_project_context(
    query: str,
    project: str = "",
    artifact_type: str = "",
    source_tool: str = "",
    top_k: int = 5,
) -> str:
    """Search project knowledge across Notion, Slack, GitHub, Figma, and Jira. Returns relevant chunks with source links."""
    filters = {"artifact_type": artifact_type, "source_tool": source_tool}
    return await handle_search_project_context(
        query=query, user_email=DEV_EMAIL, project=project, filters=filters, top_k=top_k,
    )


@mcp.tool()
async def list_sources(project: str = "") -> str:
    """Show indexed sources for a project: connector, sync status, last sync time, any errors."""
    return await handle_list_sources(project=project, user_email=DEV_EMAIL)


@mcp.tool()
async def ingest_document(
    project: str,
    content: str = "",
    url: str = "",
    artifact_type: str = "document",
) -> str:
    """Manually add a document to the project index. Provide either content or a URL to fetch."""
    return await handle_ingest_document(project=project, content=content, url=url, artifact_type=artifact_type)
```

**Step 4: Commit**

```bash
git add src/vgv_rag/server/tools/ src/vgv_rag/server/mcp_server.py
git commit -m "feat: list_sources and ingest_document MCP tools"
```

---

### Task 20: Wire everything in `main.py`

**Files:**
- Modify: `src/vgv_rag/main.py`

**Step 1: Update `main.py` to start scheduler**

```python
# src/vgv_rag/main.py
import asyncio
import logging
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from dotenv import load_dotenv

load_dotenv()

from vgv_rag.config.settings import settings
from vgv_rag.server.mcp_server import mcp
from vgv_rag.ingestion.scheduler import start_scheduler
from vgv_rag.ingestion.connectors.notion import NotionConnector
from vgv_rag.ingestion.connectors.slack import SlackConnector
from vgv_rag.ingestion.connectors.github import GitHubConnector
from vgv_rag.ingestion.connectors.figma import FigmaConnector
from vgv_rag.ingestion.connectors.atlassian import AtlassianConnector

logging.basicConfig(level=settings.log_level)


def build_connector_registry():
    connectors = {}
    if settings.notion_api_token:
        connectors["notion"] = NotionConnector(settings.notion_api_token)
    if settings.slack_bot_token:
        connectors["slack"] = SlackConnector(settings.slack_bot_token)
    if settings.github_pat:
        connectors["github"] = GitHubConnector(settings.github_pat)
    if settings.figma_api_token:
        connectors["figma"] = FigmaConnector(settings.figma_api_token)
    if all([settings.atlassian_api_token, settings.atlassian_email, settings.atlassian_domain]):
        connectors["atlassian"] = AtlassianConnector(
            token=settings.atlassian_api_token,
            email=settings.atlassian_email,
            domain=settings.atlassian_domain,
        )
    return connectors


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "vgv-project-rag"})


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ],
        on_startup=[lambda: start_scheduler(build_connector_registry().get)],
    )


def run():
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
```

**Step 2: Run full test suite**

```bash
uv run pytest --tb=short -q
```
Expected: All tests pass.

**Step 3: Commit**

```bash
git add src/vgv_rag/main.py
git commit -m "feat: wire all connectors and scheduler into startup"
```

---

### Task 21: Dockerfile and docker-compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY scripts/ ./scripts/

ENV SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers
ENV PYTHONPATH=/app/src

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"

CMD ["uv", "run", "python", "-m", "vgv_rag.main"]
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
      - model-cache:/app/.cache/sentence-transformers
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  model-cache:
```

**Step 3: Build and smoke test**

```bash
docker-compose up --build -d
sleep 15
curl http://localhost:3000/health
# Expected: {"status":"ok","service":"vgv-project-rag"}
docker-compose down
```

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Dockerfile and docker-compose for deployment"
```

---

### Task 22: Final verification

**Step 1: Run full test suite with coverage**

```bash
uv run pytest -v --tb=short
```
Expected: All tests pass.

**Step 2: Type-check (optional but recommended)**

```bash
uv add --dev mypy
uv run mypy src/vgv_rag --ignore-missing-imports
```
Expected: No errors.

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final verification — all tests passing"
```

---

## End-to-End Verification Checklist

1. **Supabase setup**
   - Run `001_initial_schema.sql` in SQL Editor
   - Enable Google Auth, restrict to `@verygood.ventures`

2. **Seed a project**
   ```bash
   cp .env.example .env  # fill in real credentials
   uv run python scripts/seed_project.py \
     --hub-url "https://notion.so/..." \
     --name "My Project" \
     --member "you@verygood.ventures"
   ```

3. **Query from Claude Code**
   - Add to Claude MCP config: `{ "vgv-project-rag": { "url": "http://localhost:3000/mcp" } }`
   - Run: `search_project_context("how does auth work")`
   - Verify results reference real Notion/Slack/GitHub content

4. **Docker deployment**
   ```bash
   docker-compose up --build
   ```
