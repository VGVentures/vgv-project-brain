import asyncio
import base64
import json
import re
from datetime import datetime
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

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


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
