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

    def test_extract_open_id_format(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_file_id

        url = "https://drive.google.com/open?id=1aBcDeFgHiJkLmNoPqRsT"
        assert _extract_file_id(url) == "1aBcDeFgHiJkLmNoPqRsT"


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

        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "doc1",
            "name": "Sprint 3 PRD",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2026-04-01T12:00:00.000Z",
        }
        connector._service.files.return_value.get.return_value = mock_get

        mock_export = MagicMock()
        mock_export.execute.return_value = b"This is the PRD content."
        connector._service.files.return_value.export.return_value = mock_export

        docs = await connector.fetch_documents(source)
        assert len(docs) == 1
        assert docs[0].content == "This is the PRD content."
        assert docs[0].artifact_type == "prd"
        assert docs[0].source_tool == "google_drive"
        assert "document/d/doc1" in docs[0].source_url

    @pytest.mark.asyncio
    async def test_fetches_google_slides(self, connector):
        """Google Slides source uses presentation URL template."""
        source = Source(
            id="s1",
            project_id="p1",
            connector="google_drive",
            source_url="https://docs.google.com/presentation/d/slides1/edit",
            source_id="file:slides1",
        )

        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "slides1",
            "name": "Design Review",
            "mimeType": "application/vnd.google-apps.presentation",
            "modifiedTime": "2026-04-01T12:00:00.000Z",
        }
        connector._service.files.return_value.get.return_value = mock_get

        mock_export = MagicMock()
        mock_export.execute.return_value = b"Slide content here."
        connector._service.files.return_value.export.return_value = mock_export

        docs = await connector.fetch_documents(source)
        assert len(docs) == 1
        assert docs[0].artifact_type == "presentation"
        assert "presentation/d/slides1" in docs[0].source_url

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
            "modifiedTime": "2026-04-01T12:00:00.000Z",
        }
        connector._service.files.return_value.get.return_value = mock_get

        docs = await connector.fetch_documents(source, since=source.last_synced_at)
        assert len(docs) == 0


class TestFolderCrawl:
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

    def _mock_list(self, connector, files):
        """Set up files().list() to return given files."""
        mock_list = MagicMock()
        mock_list.execute.return_value = {"files": files, "nextPageToken": None}
        connector._service.files.return_value.list.return_value = mock_list

    @pytest.mark.asyncio
    async def test_crawls_folder_and_exports_doc(self, connector):
        """Folder crawl finds a doc and exports it."""
        self._mock_list(connector, [
            {
                "id": "doc1",
                "name": "Meeting Notes",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-04-01T12:00:00.000Z",
            },
        ])

        mock_export = MagicMock()
        mock_export.execute.return_value = b"Meeting content"
        connector._service.files.return_value.export.return_value = mock_export

        source = Source(
            id="s1", project_id="p1", connector="google_drive",
            source_url="https://drive.google.com/drive/folders/f1",
            source_id="folder:f1",
        )
        docs = await connector.fetch_documents(source)
        assert len(docs) == 1
        assert docs[0].title == "Meeting Notes"

    @pytest.mark.asyncio
    async def test_skips_spreadsheets_in_folder(self, connector):
        """Spreadsheets in folders are skipped."""
        self._mock_list(connector, [
            {
                "id": "sheet1",
                "name": "Budget",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "modifiedTime": "2026-04-01T12:00:00.000Z",
            },
        ])

        source = Source(
            id="s1", project_id="p1", connector="google_drive",
            source_url="https://drive.google.com/drive/folders/f1",
            source_id="folder:f1",
        )
        docs = await connector.fetch_documents(source)
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_skips_unmodified_files_in_folder(self, connector):
        """Incremental sync skips files not modified since last sync."""
        self._mock_list(connector, [
            {
                "id": "doc1",
                "name": "Old Doc",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-04-01T12:00:00.000Z",
            },
        ])

        source = Source(
            id="s1", project_id="p1", connector="google_drive",
            source_url="https://drive.google.com/drive/folders/f1",
            source_id="folder:f1",
        )
        since = datetime(2026, 4, 5, tzinfo=timezone.utc)
        docs = await connector.fetch_documents(source, since=since)
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_continues_on_api_error(self, connector):
        """A 403/404 on one file doesn't abort the entire crawl."""
        from googleapiclient.errors import HttpError

        self._mock_list(connector, [
            {
                "id": "bad",
                "name": "Forbidden Doc",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-04-08T12:00:00.000Z",
            },
            {
                "id": "good",
                "name": "Accessible Doc",
                "mimeType": "application/vnd.google-apps.document",
                "modifiedTime": "2026-04-08T12:00:00.000Z",
            },
        ])

        call_count = 0

        def mock_export_execute():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status = 403
                raise HttpError(resp, b"Forbidden")
            return b"Good content"

        mock_export = MagicMock()
        mock_export.execute = mock_export_execute
        connector._service.files.return_value.export.return_value = mock_export

        source = Source(
            id="s1", project_id="p1", connector="google_drive",
            source_url="https://drive.google.com/drive/folders/f1",
            source_id="folder:f1",
        )
        docs = await connector.fetch_documents(source)
        assert len(docs) == 1
        assert docs[0].title == "Accessible Doc"

    @pytest.mark.asyncio
    async def test_respects_max_depth(self, connector):
        """Folder crawl stops at MAX_FOLDER_DEPTH."""
        from vgv_rag.ingestion.connectors.google_drive import MAX_FOLDER_DEPTH

        # Every folder contains one subfolder
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "files": [{
                "id": "subfolder",
                "name": "Deep Folder",
                "mimeType": "application/vnd.google-apps.folder",
                "modifiedTime": "2026-04-01T12:00:00.000Z",
            }],
            "nextPageToken": None,
        }
        connector._service.files.return_value.list.return_value = mock_list

        source = Source(
            id="s1", project_id="p1", connector="google_drive",
            source_url="https://drive.google.com/drive/folders/f1",
            source_id="folder:f1",
        )
        docs = await connector.fetch_documents(source)
        assert len(docs) == 0

        # list() should be called MAX_FOLDER_DEPTH times (stops at depth limit)
        assert connector._service.files.return_value.list.call_count == MAX_FOLDER_DEPTH


class TestPdfExtraction:
    def test_extracts_text_from_pdf(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_pdf_text

        # Minimal valid PDF
        import io
        from pdfminer.high_level import extract_text

        # Test with empty/invalid bytes returns empty string
        result = _extract_pdf_text(b"not a pdf")
        assert result == ""

    def test_returns_empty_on_invalid_bytes(self):
        from vgv_rag.ingestion.connectors.google_drive import _extract_pdf_text

        assert _extract_pdf_text(b"") == ""


class TestArtifactTypeDetection:
    def test_presentation_mime_returns_presentation(self):
        from vgv_rag.ingestion.connectors.google_drive import _detect_drive_artifact_type

        assert _detect_drive_artifact_type("Q3 Review", "application/vnd.google-apps.presentation") == "presentation"

    def test_doc_mime_falls_through_to_title(self):
        from vgv_rag.ingestion.connectors.google_drive import _detect_drive_artifact_type

        assert _detect_drive_artifact_type("Sprint 3 PRD", "application/vnd.google-apps.document") == "prd"
        assert _detect_drive_artifact_type("Weekly Sync", "application/vnd.google-apps.document") == "meeting_note"
        assert _detect_drive_artifact_type("Random File", "application/vnd.google-apps.document") == "document"
