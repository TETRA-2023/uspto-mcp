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

    def test_filter_invalid_verbosity(self):
        data = {"id": "1", "name": "Test"}
        result = src.server._filter_response(data, "patent_summary", "invalid")
        # Falls back to standard; with no fields registered, returns data unchanged
        assert result == data


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
