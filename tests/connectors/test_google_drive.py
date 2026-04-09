import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from vgv_rag.ingestion.connectors.types import ProjectConfig, Source


class TestUrlParsing:
    def test_extract_folder_id(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_folder_id

        url = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsT"
        assert _extract_folder_id(url) == "1aBcDeFgHiJkLmNoPqRsT"

    def test_extract_doc_id(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_file_id

        url = "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsT/edit"
        assert _extract_file_id(url) == "1aBcDeFgHiJkLmNoPqRsT"

    def test_extract_slides_id(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_file_id

        url = "https://docs.google.com/presentation/d/1xYz/edit#slide=id.p"
        assert _extract_file_id(url) == "1xYz"

    def test_extract_drive_file_id(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_file_id

        url = "https://drive.google.com/file/d/1aBcDeF/view"
        assert _extract_file_id(url) == "1aBcDeF"


class TestDiscoverSources:
    @pytest.fixture
    def connector(self):
        with patch(
            "vgv_rag.ingestion.connectors.google_drive._build_drive_service"
        ):
            from vgv_rag.ingestion.connectors.google_drive import GoogleDriveConnector

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
            from vgv_rag.ingestion.connectors.google_drive import GoogleDriveConnector

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
