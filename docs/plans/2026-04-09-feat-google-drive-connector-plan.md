# feat: Add Google Drive connector for Docs, Slides, and PDF ingestion

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Google Drive connector to the VGV Project RAG Service that indexes Google Docs, Google Slides, and PDF files from shared Drive folders and individual document links. Google Sheets are deferred to a future phase.

**Brainstorm:** `docs/brainstorm/2026-04-09-google-drive-connector-brainstorm-doc.md`

**Architecture:** A single connector class implementing the existing `Connector` Protocol. Uses `google-api-python-client` with a GCP service account for authentication. The Drive API v3 is the unified entry point — folder crawls use `files.list`, document content is extracted via `files.export` (Docs/Slides → plain text) and `pdfminer.six` (PDFs → text). Integrates into the existing scheduler, hub parser, and chunking pipeline.

**New Dependencies:** `google-api-python-client`, `google-auth`, `pdfminer.six`

---

## Task 1: Add dependencies and settings

**Files:**
- Edit: `pyproject.toml`
- Edit: `src/vgv_rag/config/settings.py`
- Edit: `.env.example`

**Step 1: Add Python dependencies**

```bash
uv add google-api-python-client google-auth pdfminer.six
```

**Step 2: Add setting to `src/vgv_rag/config/settings.py`**

Add one new optional field to the `Settings` class:

```python
# Google Drive (service account)
google_service_account_json: Optional[str] = None  # Base64-encoded JSON key or file path
```

**Step 3: Add env var to `.env.example`**

```bash
# Google Drive
GOOGLE_SERVICE_ACCOUNT_JSON=          # Base64-encoded service account JSON key, or path to key file
```

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock src/vgv_rag/config/settings.py .env.example
git commit -m "chore: add google-api-python-client and service account setting"
```

---

## Task 2: Extend ProjectConfig, URL classification, and chunker

**Files:**
- Edit: `src/vgv_rag/ingestion/connectors/types.py`
- Edit: `src/vgv_rag/ingestion/project_hub_parser.py`
- Edit: `src/vgv_rag/processing/chunker.py`
- Edit: `tests/test_project_hub_parser.py` (add Google URL tests to existing file)
- Edit: `tests/test_chunker.py` (add presentation tests to existing file)

**Step 1: Add failing tests for URL classification to `tests/test_project_hub_parser.py`**

Append to the existing test file:

```python
# --- Google Drive URL classification tests ---

@pytest.mark.parametrize("url,field", [
    # Shared folder
    ("https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsT", "google_drive_folders"),
    # Google Doc
    ("https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsT/edit", "google_drive_docs"),
    # Google Slides
    ("https://docs.google.com/presentation/d/1aBcDeFgHiJkLmNoPqRsT/edit", "google_drive_docs"),
    # Direct file link
    ("https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsT/view", "google_drive_docs"),
])
def test_classify_google_urls(url, field):
    from vgv_rag.ingestion.connectors.types import ProjectConfig
    from vgv_rag.ingestion.project_hub_parser import _classify_url

    config = ProjectConfig()
    _classify_url(url, config)
    assert url in getattr(config, field)


def test_classify_google_sheets_ignored():
    """Sheets are deferred — URLs should not be classified."""
    from vgv_rag.ingestion.connectors.types import ProjectConfig
    from vgv_rag.ingestion.project_hub_parser import _classify_url

    config = ProjectConfig()
    _classify_url("https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsT/edit", config)
    assert not config.google_drive_folders
    assert not config.google_drive_docs
```

**Step 2: Add failing test for presentation chunking to `tests/test_chunker.py`**

Append to the existing test file:

```python
def test_presentation_config_exists():
    from vgv_rag.processing.chunker import CHUNKING_CONFIG
    assert "presentation" in CHUNKING_CONFIG


def test_presentation_chunks_by_section():
    text = "# Slide 1\nIntro content\n\n# Slide 2\nMore content here"
    chunks = chunk(text, "presentation")
    assert len(chunks) >= 2
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/test_project_hub_parser.py tests/test_chunker.py -x
```

Expected: FAIL — `ProjectConfig` has no `google_drive_folders` field, no `presentation` in `CHUNKING_CONFIG`.

**Step 4: Add fields to `ProjectConfig` in `src/vgv_rag/ingestion/connectors/types.py`**

Add two new fields to the `ProjectConfig` dataclass:

```python
google_drive_folders: list[str] = field(default_factory=list)
google_drive_docs: list[str] = field(default_factory=list)
```

**Step 5: Add URL classification branches to `_classify_url` in `src/vgv_rag/ingestion/project_hub_parser.py`**

Add these branches **before** the catch-all `elif "notion.so" in url` branch:

```python
elif "docs.google.com/spreadsheets" in url:
    pass  # Sheets deferred — intentionally ignored
elif "drive.google.com/drive/folders" in url:
    config.google_drive_folders.append(url)
elif "docs.google.com" in url or "drive.google.com/file" in url:
    config.google_drive_docs.append(url)
elif "drive.google.com" in url:
    config.google_drive_folders.append(url)  # Bare drive links are likely folders
```

URL pattern rationale:
- `docs.google.com/spreadsheets` → explicit skip (Sheets deferred)
- `drive.google.com/drive/folders/ID` → folder crawl source
- `docs.google.com/document/d/ID` and `docs.google.com/presentation/d/ID` → individual doc
- `drive.google.com/file/d/ID` → individual file (PDF, etc.)
- Bare `drive.google.com` → likely a folder share link

**Step 6: Add `presentation` to `CHUNKING_CONFIG` in `src/vgv_rag/processing/chunker.py`**

```python
"presentation": ChunkConfig("by_section", 500, 0),
```

Slides exported to plain text have slide boundaries that map to H1-level sections. `by_section` splits on `^#{1,2}\s` which captures these. No overlap since slides are self-contained.

**Step 7: Run tests**

```bash
pytest tests/test_project_hub_parser.py tests/test_chunker.py -x
```

Expected: PASS.

**Step 8: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/types.py src/vgv_rag/ingestion/project_hub_parser.py \
    src/vgv_rag/processing/chunker.py tests/test_project_hub_parser.py tests/test_chunker.py
git commit -m "feat: classify Google Drive URLs in hub parser, add presentation chunking"
```

---

## Task 3: Build the Google Drive connector

**Files:**
- Create: `src/vgv_rag/ingestion/connectors/google_drive.py`
- Create: `tests/connectors/test_google_drive.py`
- Edit: `src/vgv_rag/ingestion/connectors/types.py` (extract shared `ARTIFACT_PATTERNS` + `detect_artifact_type`)
- Edit: `src/vgv_rag/ingestion/connectors/notion.py` (import shared `detect_artifact_type` instead of local copy)

This is the core task. The connector must:

1. Authenticate via GCP service account
2. Discover sources from `ProjectConfig.google_drive_folders` and `ProjectConfig.google_drive_docs`
3. Fetch documents: crawl folders recursively, export Docs/Slides to text, extract text from PDFs
4. Support incremental sync via `modifiedTime` filter

**Step 1: Write failing tests**

```python
# tests/connectors/test_google_drive.py
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from vgv_rag.ingestion.connectors.types import ProjectConfig, Source, RawDocument
from vgv_rag.ingestion.connectors.google_drive import (
    GoogleDriveConnector,
    _extract_file_id,
    _extract_folder_id,
)


class TestUrlParsing:
    def test_extract_folder_id(self):
        url = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsT"
        assert _extract_folder_id(url) == "1aBcDeFgHiJkLmNoPqRsT"

    def test_extract_doc_id(self):
        url = "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsT/edit"
        assert _extract_file_id(url) == "1aBcDeFgHiJkLmNoPqRsT"

    def test_extract_slides_id(self):
        url = "https://docs.google.com/presentation/d/1xYz/edit#slide=id.p"
        assert _extract_file_id(url) == "1xYz"

    def test_extract_drive_file_id(self):
        url = "https://drive.google.com/file/d/1aBcDeF/view"
        assert _extract_file_id(url) == "1aBcDeF"


class TestDiscoverSources:
    @pytest.fixture
    def connector(self):
        with patch(
            "vgv_rag.ingestion.connectors.google_drive._build_drive_service"
        ):
            return GoogleDriveConnector("fake-creds")

    @pytest.mark.asyncio
    async def test_discovers_folders_and_docs(self, connector):
        config = ProjectConfig(
            google_drive_folders=["https://drive.google.com/drive/folders/folder1"],
            google_drive_docs=["https://docs.google.com/document/d/doc1/edit"],
        )
        sources = await connector.discover_sources(config)
        assert len(sources) == 2
        assert sources[0]["connector"] == "google_drive"
        assert sources[0]["source_id"] == "folder:folder1"
        assert sources[1]["source_id"] == "file:doc1"


class TestFetchDocuments:
    @pytest.fixture
    def connector(self):
        with patch(
            "vgv_rag.ingestion.connectors.google_drive._build_drive_service"
        ) as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            conn = GoogleDriveConnector("fake-creds")
            conn._service = mock_service
            return conn

    @pytest.mark.asyncio
    async def test_fetches_google_doc(self, connector):
        """Individual Google Doc source returns a RawDocument."""
        source = Source(
            id="s1",
            project_id="p1",
            connector="google_drive",
            source_url="https://docs.google.com/document/d/doc1/edit",
            source_id="file:doc1",
        )

        # Mock files().get() for metadata
        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "doc1",
            "name": "Sprint 3 PRD",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2026-04-01T12:00:00.000Z",
        }
        connector._service.files.return_value.get.return_value = mock_get

        # Mock files().export() for content
        mock_export = MagicMock()
        mock_export.execute.return_value = b"This is the PRD content."
        connector._service.files.return_value.export.return_value = mock_export

        docs = await connector.fetch_documents(source)
        assert len(docs) == 1
        assert docs[0].content == "This is the PRD content."
        assert docs[0].artifact_type == "prd"
        assert docs[0].source_tool == "google_drive"

    @pytest.mark.asyncio
    async def test_skips_unmodified_doc(self, connector):
        """Documents not modified since last sync are skipped."""
        source = Source(
            id="s1",
            project_id="p1",
            connector="google_drive",
            source_url="https://docs.google.com/document/d/doc1/edit",
            source_id="file:doc1",
            last_synced_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
        )

        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "doc1",
            "name": "Old Doc",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2026-04-01T12:00:00.000Z",  # Before last sync
        }
        connector._service.files.return_value.get.return_value = mock_get

        docs = await connector.fetch_documents(source, since=source.last_synced_at)
        assert len(docs) == 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/connectors/test_google_drive.py -x
```

Expected: FAIL — module `google_drive` not found.

**Step 3: Write `src/vgv_rag/ingestion/connectors/google_drive.py`**

Note: `ARTIFACT_PATTERNS` must be extracted from `src/vgv_rag/ingestion/connectors/notion.py` into `types.py` as a shared constant, then imported by both `notion.py` and `google_drive.py`. This prevents drift between connectors classifying the same title differently. Add a `detect_artifact_type(title: str) -> str` function to `types.py` and update the Notion connector to import it.

```python
# src/vgv_rag/ingestion/connectors/google_drive.py
import asyncio
import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from vgv_rag.ingestion.connectors.types import (
    ProjectConfig, RawDocument, Source, detect_artifact_type,
)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Workspace MIME types that can be exported to text
EXPORTABLE_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
}

# MIME types to skip entirely
SKIP_MIMES = {
    "application/vnd.google-apps.spreadsheet",  # Sheets deferred
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.map",
}

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB — skip PDFs larger than this


def _detect_drive_artifact_type(title: str, mime_type: str) -> str:
    if mime_type == "application/vnd.google-apps.presentation":
        return "presentation"
    return detect_artifact_type(title)


def _extract_folder_id(url: str) -> str:
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else url


def _extract_file_id(url: str) -> str:
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else url


def _build_drive_service(credentials: str):
    """Build a Google Drive API service from a service account credential.

    credentials can be:
    - A file path to a JSON key file
    - A base64-encoded JSON key string
    """
    if Path(credentials).is_file():
        creds = Credentials.from_service_account_file(credentials, scopes=SCOPES)
    else:
        key_data = json.loads(base64.b64decode(credentials))
        creds = Credentials.from_service_account_info(key_data, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def _parse_modified_time(time_str: str) -> datetime:
    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))


class GoogleDriveConnector:
    def __init__(self, credentials: str):
        self._service = _build_drive_service(credentials)

    async def discover_sources(self, config: ProjectConfig) -> list[dict]:
        sources = []
        for url in config.google_drive_folders:
            folder_id = _extract_folder_id(url)
            sources.append({
                "connector": "google_drive",
                "source_url": url,
                "source_id": f"folder:{folder_id}",
            })
        for url in config.google_drive_docs:
            file_id = _extract_file_id(url)
            sources.append({
                "connector": "google_drive",
                "source_url": url,
                "source_id": f"file:{file_id}",
            })
        return sources

    async def fetch_documents(
        self, source: Source, since: datetime | None = None
    ) -> list[RawDocument]:
        source_id = source.source_id
        if source_id.startswith("folder:"):
            folder_id = source_id.removeprefix("folder:")
            docs: list[RawDocument] = []
            await self._crawl_folder(folder_id, since, docs)
            return docs
        else:
            file_id = source_id.removeprefix("file:")
            return await self._fetch_single_file(file_id, since)

    async def _crawl_folder(
        self, folder_id: str, since: datetime | None, docs: list[RawDocument]
    ) -> None:
        query_parts = [f"'{folder_id}' in parents", "trashed = false"]
        if since:
            query_parts.append(f"modifiedTime > '{since.isoformat()}'")

        page_token = None
        while True:
            result = await asyncio.to_thread(
                lambda pt=page_token: self._service.files()
                .list(
                    q=" and ".join(query_parts),
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                    pageSize=100,
                    pageToken=pt,
                )
                .execute()
            )

            for file in result.get("files", []):
                mime = file["mimeType"]

                # Recurse into subfolders
                if mime == "application/vnd.google-apps.folder":
                    await self._crawl_folder(file["id"], since, docs)
                    continue

                if mime in SKIP_MIMES:
                    continue

                doc = await self._extract_document(file)
                if doc:
                    docs.append(doc)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    async def _fetch_single_file(
        self, file_id: str, since: datetime | None
    ) -> list[RawDocument]:
        metadata = await asyncio.to_thread(
            lambda: self._service.files()
            .get(fileId=file_id, fields="id, name, mimeType, modifiedTime, size")
            .execute()
        )

        modified = _parse_modified_time(metadata["modifiedTime"])
        if since and modified <= since:
            return []

        doc = await self._extract_document(metadata)
        return [doc] if doc else []

    async def _extract_document(self, file: dict) -> RawDocument | None:
        """Extract text content from a Drive file, return None if not extractable."""
        file_id = file["id"]
        mime = file["mimeType"]
        name = file["name"]
        modified = _parse_modified_time(file["modifiedTime"])

        # Google Workspace documents — export to plain text
        if mime in EXPORTABLE_MIMES:
            export_mime = EXPORTABLE_MIMES[mime]
            content_bytes = await asyncio.to_thread(
                lambda: self._service.files()
                .export(fileId=file_id, mimeType=export_mime)
                .execute()
            )
            content = content_bytes.decode("utf-8", errors="replace").strip()
            if not content:
                return None
            return RawDocument(
                source_url=f"https://docs.google.com/document/d/{file_id}",
                content=content,
                title=name,
                date=modified,
                artifact_type=_detect_drive_artifact_type(name, mime),
                source_tool="google_drive",
            )

        # PDFs — download and extract text
        if mime == "application/pdf":
            size = int(file.get("size", 0))
            if size > MAX_PDF_BYTES:
                return None

            content_bytes = await asyncio.to_thread(
                lambda: self._service.files()
                .get_media(fileId=file_id)
                .execute()
            )
            content = _extract_pdf_text(content_bytes)
            if not content:
                return None
            return RawDocument(
                source_url=f"https://drive.google.com/file/d/{file_id}/view",
                content=content,
                title=name,
                date=modified,
                artifact_type=_detect_drive_artifact_type(name, mime),
                source_tool="google_drive",
            )

        # Other binary files — skip
        return None


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfminer.six."""
    from pdfminer.high_level import extract_text
    import io

    try:
        return extract_text(io.BytesIO(pdf_bytes)).strip()
    except Exception:
        return ""
```

**Step 4: Run tests**

```bash
pytest tests/connectors/test_google_drive.py -x
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/vgv_rag/ingestion/connectors/google_drive.py \
    src/vgv_rag/ingestion/connectors/types.py \
    src/vgv_rag/ingestion/connectors/notion.py \
    tests/connectors/test_google_drive.py
git commit -m "feat: Google Drive connector with folder crawl, Docs/Slides export, PDF extraction"
```

---

## Task 4: Register connector in startup

**Files:**
- Edit: `src/vgv_rag/main.py`

**Step 1: Add Google Drive connector to `build_connector_registry()`**

Add after the Atlassian connector block:

```python
if settings.google_service_account_json:
    from vgv_rag.ingestion.connectors.google_drive import GoogleDriveConnector
    connectors["google_drive"] = GoogleDriveConnector(credentials=settings.google_service_account_json)
```

**Step 2: Verify existing tests still pass**

```bash
pytest -x
```

**Step 3: Commit**

```bash
git add src/vgv_rag/main.py
git commit -m "feat: register Google Drive connector in startup"
```

---

## Task 5: Update CLAUDE.md and documentation

**Files:**
- Edit: `CLAUDE.md`

**Step 1: Update CLAUDE.md**

Add `google_drive.py` to the project structure listing under `connectors/`. Update the Architecture diagram and Tech Stack table to include Google Drive. Add `GOOGLE_SERVICE_ACCOUNT_JSON` to the Environment Variables section.

Update the connector list in these sections:
- Architecture diagram description
- Connector Details (add a **Google Drive Connector** section)
- Onboarding instructions (mention sharing folders with the service account email)

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Google Drive connector to CLAUDE.md"
```

---

## Edge Cases and Error Handling

These should be handled within the connector implementation (Task 4):

| Scenario | Handling |
|----------|----------|
| Service account lacks access to a folder/doc | Catch `HttpError(403)` or `HttpError(404)`, skip the file, don't fail the entire sync. Note: service accounts get 404 (not 403) when lacking access — error handling should suggest checking sharing permissions |
| PDF exceeds 10 MB size limit | Skip silently — `_extract_document` returns `None` |
| Google Sheets URL in Drive folder | `SKIP_MIMES` set filters it out during folder crawl |
| Empty Google Doc (no content) | `_extract_document` returns `None`, skipped |
| Drive API rate limit (403 rate limit) | Let it bubble up to scheduler retry logic — same as other connectors |
| Deeply nested folder structure | Recursive crawl with no depth limit; Drive API handles pagination |
| Google Drive shortcuts (aliases) | `files.list` returns shortcuts as `application/vnd.google-apps.shortcut` — skip via default fallthrough in `_extract_document` |
| File in trash | Filtered by `trashed = false` in query |
| Incremental sync on folders without `modifiedTime` filter on subfolders | Subfolder `modifiedTime` changes when contents change — the query handles this correctly |

## Testing Summary

| Test file | What it covers |
|-----------|----------------|
| `tests/test_project_hub_parser.py` | Existing tests + new Google URL classification tests |
| `tests/test_chunker.py` | Existing tests + new `presentation` artifact type test |
| `tests/connectors/test_google_drive.py` | URL parsing, source discovery, document fetching, incremental sync |

## Acceptance Criteria

- [ ] Google Drive folder URLs from Hub "Helpful Links" are classified into `ProjectConfig.google_drive_folders`
- [ ] Individual Google Doc/Slides URLs are classified into `ProjectConfig.google_drive_docs`
- [ ] Google Sheets URLs are explicitly ignored (not classified)
- [ ] Connector recursively crawls shared Drive folders
- [ ] Google Docs are exported to plain text and chunked
- [ ] Google Slides are exported to plain text and chunked as `presentation` artifact type
- [ ] PDFs under 10 MB are extracted to text and chunked
- [ ] PDFs over 10 MB are skipped
- [ ] Incremental sync respects `modifiedTime` for both folders and individual docs
- [ ] Connector is registered and runs on the cron schedule alongside other connectors
- [ ] All tests pass
