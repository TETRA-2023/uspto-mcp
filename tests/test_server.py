"""Unit tests for USPTO MCP server."""

from unittest.mock import AsyncMock

import pytest

import src.server
from src.uspto_client import UsptoClient


@pytest.fixture
def mock_client():
    """Create a mocked UsptoClient and inject it as the global client."""
    client = AsyncMock(spec=UsptoClient)
    original = src.server._client
    src.server._client = client
    yield client
    src.server._client = original


class TestPpubsTools:
    @pytest.mark.asyncio
    async def test_check_ppubs_status_reachable(self, mock_client):
        mock_client.check_ppubs_status.return_value = {
            "reachable": True,
            "status_code": 200,
            "url": "https://ppubs.uspto.gov",
        }
        result = await src.server.check_ppubs_status()
        assert result["reachable"] is True
        assert result["status_code"] == 200
        mock_client.check_ppubs_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_ppubs_status_unreachable(self, mock_client):
        mock_client.check_ppubs_status.return_value = {
            "reachable": False,
            "status_code": None,
            "url": "https://ppubs.uspto.gov",
            "error": "ConnectError: dns failure",
        }
        result = await src.server.check_ppubs_status()
        assert result["reachable"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ppubs_search_patents_envelope(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 140619,
            "totalResults": 2,
            "page": 0,
            "perPage": 2,
            "totalPages": 70310,
            "patents": [
                {
                    "guid": "US-20260126277-A1",
                    "type": "US-PGPUB",
                    "publicationReferenceDocumentNumber": "20260126277",
                    "applicationNumber": "18/932154",
                    "inventionTitle": "POLYMERIC CARTRIDGE ASSEMBLY",
                    "datePublished": "2026-05-07T00:00:00Z",
                    "applicantName": ["Battaglia; Vincent"],
                    "mainClassificationCode": "1/1",
                    "ipcCodeFlattened": "F42B5/307",
                    "cpcInventiveFlattened": "F42B5/307",
                    "applicationFilingDate": ["2024-10-30T00:00:00Z"],
                    "frontPageStart": 1,
                },
                {
                    "guid": "US-1234567-B2",
                    "type": "USPAT",
                    "publicationReferenceDocumentNumber": "1234567",
                    "applicationNumber": "10/000001",
                    "inventionTitle": "WIDGET",
                    "datePublished": "2020-01-01T00:00:00Z",
                    "applicantName": ["Doe; Jane"],
                    "mainClassificationCode": "2/2",
                    "ipcCodeFlattened": "G06F1/00",
                    "cpcInventiveFlattened": "G06F1/00",
                    "applicationFilingDate": ["2018-01-01T00:00:00Z"],
                    "frontPageStart": 1,
                },
            ],
        }
        result = await src.server.ppubs_search_patents("graphene", limit=2)
        assert result["total"] == 2
        assert result["num_found"] == 140619
        assert len(result["results"]) == 2
        # standard verbosity strips frontPageStart but keeps title + filing date
        assert "frontPageStart" not in result["results"][0]
        assert result["results"][0]["inventionTitle"] == "POLYMERIC CARTRIDGE ASSEMBLY"
        assert result["results"][0]["applicationFilingDate"] == ["2024-10-30T00:00:00Z"]
        mock_client.ppubs_search_patents.assert_called_once_with(
            query="graphene", limit=2, start=0, sort="date_publ desc", sources=None
        )

    @pytest.mark.asyncio
    async def test_ppubs_search_patents_minimal(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 1,
            "totalResults": 1,
            "page": 0,
            "perPage": 1,
            "totalPages": 1,
            "patents": [
                {
                    "guid": "US-1-A1",
                    "type": "US-PGPUB",
                    "publicationReferenceDocumentNumber": "1",
                    "inventionTitle": "T",
                    "datePublished": "2024-01-01T00:00:00Z",
                    "applicationNumber": "00/0",
                    "applicantName": ["X"],
                    "mainClassificationCode": "1",
                    "ipcCodeFlattened": "A",
                    "cpcInventiveFlattened": "A",
                }
            ],
        }
        result = await src.server.ppubs_search_patents("x", verbosity="minimal")
        # minimal drops applicationNumber, applicantName, classification fields
        record = result["results"][0]
        assert "applicationNumber" not in record
        assert "applicantName" not in record
        assert "guid" in record
        assert "inventionTitle" in record


class TestResponseFiltering:
    def test_filter_full_returns_all(self):
        data = {"id": "1", "name": "Test", "extra": "field"}
        result = src.server._filter_response(data, "patent_detail", "full")
        assert result == data

    def test_filter_unknown_type(self):
        data = {"id": "1", "custom": "value"}
        result = src.server._filter_response(data, "unknown_type", "standard")
        assert result == data

    def test_filter_none_input(self):
        result = src.server._filter_response(None, "patent_summary", "standard")
        assert result is None

    def test_filter_invalid_verbosity_falls_back_to_standard(self):
        data = {
            "guid": "g",
            "type": "USPAT",
            "publicationReferenceDocumentNumber": "1",
            "inventionTitle": "T",
            "datePublished": "2024-01-01T00:00:00Z",
            "applicationNumber": "00/0",
            "applicantName": ["X"],
            "mainClassificationCode": "1",
            "ipcCodeFlattened": "A",
            "cpcInventiveFlattened": "A",
            "applicationFilingDate": ["2020-01-01T00:00:00Z"],
            "frontPageStart": 1,
        }
        result = src.server._filter_response(data, "patent_summary", "invalid")
        # Falls back to standard verbosity — drops frontPageStart, keeps the rest
        assert "frontPageStart" not in result
        assert result["guid"] == "g"
        assert result["applicationNumber"] == "00/0"


class TestTransportResolution:
    def test_default_stdio(self):
        assert src.server._resolve_transport(argv=[], env={}) == "stdio"

    def test_sse_flag(self):
        assert src.server._resolve_transport(argv=["--sse"], env={}) == "sse"

    def test_streamable_http_flag(self):
        assert (
            src.server._resolve_transport(argv=["--streamable-http"], env={}) == "streamable-http"
        )

    def test_env_var(self):
        assert src.server._resolve_transport(argv=[], env={"USPTO_TRANSPORT": "sse"}) == "sse"

    def test_cli_overrides_env(self):
        result = src.server._resolve_transport(
            argv=["--streamable-http"], env={"USPTO_TRANSPORT": "sse"}
        )
        assert result == "streamable-http"

    def test_invalid_env(self):
        assert src.server._resolve_transport(argv=[], env={"USPTO_TRANSPORT": "invalid"}) == "stdio"
