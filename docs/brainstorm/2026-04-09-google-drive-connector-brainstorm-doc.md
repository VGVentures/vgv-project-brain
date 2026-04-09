---
date: 2026-04-09
topic: google-drive-connector
---

# Google Drive/Docs/Slides Connector for VGV Project RAG Service

## What We're Building

A single Google Drive connector that indexes Google Docs, Google Slides, and files (PDFs, etc.) from shared Drive folders and individual document links into the RAG pipeline. Uses a GCP service account for authentication and the Google Drive API v3 as the unified entry point. Google Sheets are deferred to a later phase due to their fundamentally different structure (tabular data vs. prose).

The connector follows the existing `Connector` Protocol pattern: `discover_sources` parses folder/doc URLs from `ProjectConfig`, and `fetch_documents` crawls folders recursively or fetches individual documents, exporting native Google formats to plain text.

## Why This Approach

Three approaches were considered:

1. **Single Drive connector (chosen)** -- One connector using Drive API for folder crawls + individual doc links. Exports Docs/Slides to plain text via `files.export()`, extracts text from PDFs via `pdfminer.six`. Matches the existing connector pattern cleanly.

2. **Separate connectors per Google type** -- Dedicated connectors for Docs API, Slides API, and Drive files. Richer structural extraction but over-engineered for v1 (three connectors, three config fields, more Hub parser complexity).

3. **Folder crawl only** -- Only crawl shared folders, rely on `ingest_document` for individual links. Simplest but breaks the automatic sync contract that other connectors provide.

The single connector wins because it covers both usage patterns (folders + individual links), uses one auth setup, and integrates cleanly with the existing codebase patterns.

## Key Decisions

- **Auth: GCP service account** -- No user interaction needed. Content is accessible by sharing Drive folders/docs with the service account email. Consistent with how other connectors use server-side credentials.
- **Content scope: Docs, Slides, PDFs (not Sheets)** -- Sheets require tabular-aware chunking that doesn't fit the existing text-based pipeline. Deferred to a later phase.
- **Hub parser handles both folder URLs and individual doc links** -- `_classify_url` matches `drive.google.com` and `docs.google.com/document` patterns, storing them in `ProjectConfig.google_drive_folders` and `ProjectConfig.google_drive_docs` respectively.
- **Text extraction strategy**:
  - Google Docs: `files.export(mimeType='text/plain')` -- loses formatting but captures all text content
  - Google Slides: `files.export(mimeType='text/plain')` -- exports speaker notes + slide text
  - PDFs: `pdfminer.six` for text extraction -- lightweight, no external binary dependencies
- **Artifact types**: Google Docs map to existing types via title detection (same `detectArtifactType` patterns -- meeting notes, PRDs, etc.). Slides map to a new `presentation` type. PDFs map to `document`.
- **Incremental sync**: Drive API supports `modifiedTime > '{timestamp}'` filter on `files.list()`. Individual docs check `modifiedTime` via `files.get()`.
- **New dependency**: `google-api-python-client` + `google-auth` for Drive API, `pdfminer.six` for PDF text extraction.
- **New env vars**: `GOOGLE_SERVICE_ACCOUNT_JSON` (the service account key JSON, base64-encoded or file path).

## Integration Points

These existing files need changes:

| File | Change |
|------|--------|
| `src/vgv_rag/config/settings.py` | Add `GOOGLE_SERVICE_ACCOUNT_JSON` field |
| `src/vgv_rag/ingestion/connectors/types.py` | Add `google_drive_folders` and `google_drive_docs` to `ProjectConfig` |
| `src/vgv_rag/ingestion/project_hub_parser.py` | Add `drive.google.com` and `docs.google.com` branches to `_classify_url` |
| `src/vgv_rag/ingestion/connectors/` | New `google_drive.py` implementing the `Connector` Protocol |
| `src/vgv_rag/main.py` | Register `google_drive` connector in `build_connector_registry()` |
| `src/vgv_rag/processing/chunker.py` | Add `presentation` artifact type to `CHUNKING_CONFIG` |
| `.env.example` | Add `GOOGLE_SERVICE_ACCOUNT_JSON` |

## Open Questions

- Should Slides be chunked per-slide (export via Slides API for slide-level granularity) or as a single text blob (Drive API export)? Per-slide is richer but requires the Slides API as a secondary dependency.
- What's the max file size threshold for PDFs before skipping? Large PDFs (e.g., exported design files) could be very slow to process.
- Should the connector index file comments/suggestions on Google Docs, or just the document body?
- How should the connector handle Google Drive shortcuts (aliases) vs actual files?
