"""Unit tests for USPTO MCP server."""

from unittest.mock import AsyncMock

import httpx
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
                    "kindCode": ["A1"],
                    "publicationReferenceDocumentNumber": "20260126277",
                    "applicationNumber": "18/932154",
                    "inventionTitle": "POLYMERIC CARTRIDGE ASSEMBLY",
                    "datePublished": "2026-05-07T00:00:00Z",
                    "inventorsShort": "",  # often empty pre-grant for US-PGPUB
                    "applicantName": ["Battaglia; Vincent"],
                    "assigneeName": [],
                    "mainClassificationCode": "1/1",
                    "ipcCodeFlattened": "F42B5/307",
                    "cpcInventiveFlattened": "F42B5/307",
                    "applicationFilingDate": ["2024-10-30T00:00:00Z"],
                    "frontPageStart": 1,
                },
                {
                    "guid": "US-1234567-B2",
                    "type": "USPAT",
                    "kindCode": ["B2"],
                    "publicationReferenceDocumentNumber": "1234567",
                    "applicationNumber": "10/000001",
                    "inventionTitle": "WIDGET",
                    "datePublished": "2020-01-01T00:00:00Z",
                    "inventorsShort": "Doe; Jane et al.",
                    "applicantName": ["Doe; Jane"],
                    "assigneeName": ["Acme Corp"],
                    "mainClassificationCode": "2/2",
                    "ipcCodeFlattened": "G06F1/00",
                    "cpcInventiveFlattened": "G06F1/00",
                    "cpcAdditionalFlattened": "G06F1/01",
                    "familyIdentifierCur": 12345,
                    "primaryExaminer": "Smith; John",
                    "score": 9.876,
                    "applicationFilingDate": ["2018-01-01T00:00:00Z"],
                    "frontPageStart": 1,
                    "datePublishedKwicHits": ["2020"],  # KWIC noise — must be filtered out
                },
            ],
        }
        result = await src.server.ppubs_search_patents("graphene", limit=2)
        assert result["total"] == 2
        assert result["num_found"] == 140619
        assert len(result["results"]) == 2
        # standard verbosity strips frontPageStart but keeps title + filing date
        # + the new inventor/assignee/kind fields
        first = result["results"][0]
        second = result["results"][1]
        assert "frontPageStart" not in first
        assert first["inventionTitle"] == "POLYMERIC CARTRIDGE ASSEMBLY"
        assert first["applicationFilingDate"] == ["2024-10-30T00:00:00Z"]
        assert first["kindCode"] == ["A1"]
        assert "inventorsShort" in first  # surfaces even when empty for US-PGPUB
        assert "assigneeName" in first
        assert second["inventorsShort"] == "Doe; Jane et al."
        assert second["assigneeName"] == ["Acme Corp"]
        assert second["kindCode"] == ["B2"]
        assert second["familyIdentifierCur"] == 12345
        assert second["primaryExaminer"] == "Smith; John"
        assert second["score"] == 9.876
        assert second["cpcAdditionalFlattened"] == "G06F1/01"
        # KWIC-noise fields must not survive standard filter
        assert "datePublishedKwicHits" not in second
        assert "frontPageStart" not in second
        mock_client.ppubs_search_patents.assert_called_once_with(
            query="graphene", limit=2, start=0, sort="date_publ desc", sources=None
        )

    @pytest.mark.asyncio
    async def test_ppubs_get_patent_by_number_found(self, mock_client):
        mock_client.ppubs_get_patent_by_number.return_value = {
            "guid": "US-6103599-A",
            "type": "USPAT",
            "inventionTitle": "Planarizing technique for multilayered substrates",
            "datePublished": "2000-08-15T00:00:00Z",
            "applicationNumber": "09/089931",
            "applicationFilingDate": ["1998-06-03T00:00:00Z"],
            "kindCode": ["A"],
            "inventorsShort": "Henley; Francois J. et al.",
            "inventorsName": ["Henley; Francois J.", "Cheung; Nathan"],
            "applicantName": [],
            "assigneeName": ["Silicon Genesis Corporation"],
            "assigneeCity": ["Los Gatos"],
            "assigneeState": ["CA"],
            "assigneeCountry": [],
            "mainClassificationCode": "438/459",
            "ipcCodeFlattened": "H01L21/70",
            "cpcInventiveFlattened": "H10P50/642;H10P90/1916;H10W10/181",
            "cpcAdditionalFlattened": "Y10S438/977",
            "familyIdentifierCur": 26732223,
            "abstractHtml": "The present invention provides...",
            "claimsHtml": "1. A method for fabricating a substrate...",
            "abstractStart": 1,
            "abstractEnd": 2,
            "claimsStart": 10,
            "claimsEnd": 11,
            "specificationStart": 7,
            "specificationEnd": 10,
            "drawingsStart": 3,
            "drawingsEnd": 6,
            "continuityData": ["This application claims the benefit of..."],
            "primaryExaminer": "Mulpuri; Savitri",
            "assistantExaminer": None,
            "legalFirmName": ["Townsend and Townsend and Crew LLP"],
            "attorneyName": None,
            "numberOfClaims": "28",
            "numberOfDrawingSheets": "4",
            "numberOfFigures": "7",
            "extraField": "should be stripped at standard",
            "abstractedPublicationDerwent": "noise",  # Derwent metadata — must be filtered
            "applicationFilingDateKwicHits": ["1998"],  # KWIC noise — must be filtered
        }
        result = await src.server.ppubs_get_patent_by_number("6103599")
        assert result["found"] is True
        assert result["publication_number"] == "6103599"
        record = result["record"]
        assert record["guid"] == "US-6103599-A"
        assert record["assigneeName"] == ["Silicon Genesis Corporation"]
        assert record["inventorsShort"] == "Henley; Francois J. et al."
        assert record["inventorsName"] == ["Henley; Francois J.", "Cheung; Nathan"]
        assert record["abstractHtml"].startswith("The present invention")
        assert record["legalFirmName"] == ["Townsend and Townsend and Crew LLP"]
        assert record["continuityData"] == ["This application claims the benefit of..."]
        assert record["primaryExaminer"] == "Mulpuri; Savitri"
        assert record["numberOfClaims"] == "28"
        assert record["numberOfDrawingSheets"] == "4"
        assert record["drawingsStart"] == 3
        assert record["drawingsEnd"] == 6
        # Standard verbosity strips: arbitrary keys, KWIC noise, Derwent metadata
        assert "extraField" not in record
        assert "abstractedPublicationDerwent" not in record
        assert "applicationFilingDateKwicHits" not in record
        mock_client.ppubs_get_patent_by_number.assert_called_once_with("6103599")

    @pytest.mark.asyncio
    async def test_ppubs_get_patent_by_number_not_found(self, mock_client):
        mock_client.ppubs_get_patent_by_number.return_value = None
        result = await src.server.ppubs_get_patent_by_number("0")
        assert result == {"found": False, "publication_number": "0"}

    @pytest.mark.asyncio
    async def test_ppubs_get_patent_by_number_minimal(self, mock_client):
        mock_client.ppubs_get_patent_by_number.return_value = {
            "guid": "US-6103599-A",
            "type": "USPAT",
            "inventionTitle": "Planarizing technique",
            "datePublished": "2000-08-15T00:00:00Z",
            "applicationNumber": "09/089931",
            "kindCode": ["A"],
            "inventorsShort": "Henley; Francois J. et al.",
            "inventorsName": ["Henley; Francois J.", "Cheung; Nathan"],
            "abstractHtml": "Abstract...",
            "claimsHtml": "Claims...",
            "assigneeName": ["Silicon Genesis Corporation"],
        }
        result = await src.server.ppubs_get_patent_by_number("6103599", verbosity="minimal")
        record = result["record"]
        assert "abstractHtml" in record
        assert record["inventorsShort"] == "Henley; Francois J. et al."  # minimal keeps short form
        assert "inventorsName" not in record  # minimal drops the per-inventor list
        assert "claimsHtml" not in record  # minimal drops claims
        assert "assigneeName" not in record  # minimal drops assignee

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
                    "kindCode": ["A1"],
                    "publicationReferenceDocumentNumber": "1",
                    "inventionTitle": "T",
                    "datePublished": "2024-01-01T00:00:00Z",
                    "applicationNumber": "00/0",
                    "applicantName": ["X"],
                    "assigneeName": [],
                    "mainClassificationCode": "1",
                    "ipcCodeFlattened": "A",
                    "cpcInventiveFlattened": "A",
                }
            ],
        }
        result = await src.server.ppubs_search_patents("x", verbosity="minimal")
        # minimal keeps guid/type/kindCode/pub#/title/date and drops the rest
        record = result["results"][0]
        assert "applicationNumber" not in record
        assert "applicantName" not in record
        assert "assigneeName" not in record
        assert "guid" in record
        assert "inventionTitle" in record
        assert record["kindCode"] == ["A1"]  # surfaces in minimal so callers can disambiguate

    @pytest.mark.asyncio
    async def test_ppubs_get_search_count(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 140619,
            "q": "graphene",
            "queryName": "graphene",
            "databaseFilters": [
                {"databaseName": "US-PGPUB", "countryCodes": []},
                {"databaseName": "USPAT", "countryCodes": []},
                {"databaseName": "USOCR", "countryCodes": []},
            ],
        }
        result = await src.server.ppubs_get_search_count("graphene")
        assert result["total"] == 140619
        assert result["query"] == "graphene"
        assert result["sources"] == ["US-PGPUB", "USPAT", "USOCR"]
        mock_client.ppubs_count_patents.assert_called_once_with(query="graphene", sources=None)

    @pytest.mark.asyncio
    async def test_ppubs_get_search_count_custom_sources(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 5,
            "q": "graphene",
            "databaseFilters": [{"databaseName": "USPAT", "countryCodes": []}],
        }
        result = await src.server.ppubs_get_search_count("graphene", sources=["USPAT"])
        assert result["total"] == 5
        assert result["sources"] == ["USPAT"]
        mock_client.ppubs_count_patents.assert_called_once_with(query="graphene", sources=["USPAT"])


class TestAutoBrs:
    def test_single_token_passthrough(self):
        assert UsptoClient._auto_brs("graphene") == "graphene"

    def test_multi_word_nl_joined_with_and(self):
        assert UsptoClient._auto_brs("graphene battery") == "graphene AND battery"

    def test_four_word_nl(self):
        assert (
            UsptoClient._auto_brs("CRISPR gene editing cancer")
            == "CRISPR AND gene AND editing AND cancer"
        )

    def test_existing_and_passthrough(self):
        assert UsptoClient._auto_brs("graphene AND battery") == "graphene AND battery"

    def test_existing_or_passthrough(self):
        assert UsptoClient._auto_brs("graphene OR battery") == "graphene OR battery"

    def test_existing_not_passthrough(self):
        assert UsptoClient._auto_brs("graphene NOT battery") == "graphene NOT battery"

    def test_field_code_passthrough(self):
        assert UsptoClient._auto_brs('("6103599").pn.') == '("6103599").pn.'

    def test_parentheses_passthrough(self):
        assert UsptoClient._auto_brs("(graphene OR battery)") == "(graphene OR battery)"

    def test_double_quote_flat_no_outer_ops(self):
        # Quoted phrase, no outer operators → flatten to AND
        assert UsptoClient._auto_brs('"prior art"') == "prior AND art"

    def test_quoted_phrase_with_surrounding_words_flattened(self):
        # "quantum dot" display smartphone → flatten all
        assert UsptoClient._auto_brs('"quantum dot" display smartphone') == (
            "quantum AND dot AND display AND smartphone"
        )

    def test_quoted_phrase_outer_ops_expand_in_phrase(self):
        # Outer AND/OR present → expand inside phrases only
        result = UsptoClient._auto_brs('("quantum dot" OR QLED) AND display')
        assert result == "((quantum AND dot) OR QLED) AND display"

    def test_mixed_quotes_outer_ops_multiple_phrases(self):
        result = UsptoClient._auto_brs('"quantum dot" AND ("mobile" OR "portable" OR smartphone)')
        assert result == "(quantum AND dot) AND (mobile OR portable OR smartphone)"

    def test_lowercase_and_is_not_brs(self):
        assert UsptoClient._auto_brs("graphene and battery") == "graphene AND and AND battery"

    @pytest.mark.asyncio
    async def test_search_nl_query_rewritten(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 53254,
            "totalResults": 53254,
            "page": 0,
            "perPage": 1,
            "totalPages": 53254,
            "patents": [],
        }
        await src.server.ppubs_search_patents("graphene battery", limit=1)
        mock_client.ppubs_search_patents.assert_called_once_with(
            query="graphene AND battery", limit=1, start=0, sort="date_publ desc", sources=None
        )

    @pytest.mark.asyncio
    async def test_search_brs_query_not_rewritten(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 53254,
            "totalResults": 53254,
            "page": 0,
            "perPage": 1,
            "totalPages": 53254,
            "patents": [],
        }
        await src.server.ppubs_search_patents("graphene AND battery", limit=1)
        mock_client.ppubs_search_patents.assert_called_once_with(
            query="graphene AND battery", limit=1, start=0, sort="date_publ desc", sources=None
        )

    @pytest.mark.asyncio
    async def test_count_nl_query_rewritten(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 53254,
            "q": "graphene AND battery",
            "databaseFilters": [{"databaseName": "USPAT", "countryCodes": []}],
        }
        await src.server.ppubs_get_search_count("graphene battery")
        mock_client.ppubs_count_patents.assert_called_once_with(
            query="graphene AND battery", sources=None
        )

    @pytest.mark.asyncio
    async def test_count_brs_query_not_rewritten(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 53254,
            "q": "graphene AND battery",
            "databaseFilters": [{"databaseName": "USPAT", "countryCodes": []}],
        }
        await src.server.ppubs_get_search_count("graphene AND battery")
        mock_client.ppubs_count_patents.assert_called_once_with(
            query="graphene AND battery", sources=None
        )


class TestZeroResultAutoRetry:
    @pytest.mark.asyncio
    async def test_search_zero_with_phrase_triggers_auto_retry(self, mock_client):
        mock_client.ppubs_search_patents.side_effect = [
            {
                "numFound": 0,
                "totalResults": 0,
                "page": 0,
                "perPage": 10,
                "totalPages": 0,
                "patents": [],
            },
            {
                "numFound": 42,
                "totalResults": 42,
                "page": 0,
                "perPage": 10,
                "totalPages": 5,
                "patents": [],
            },
        ]
        result = await src.server.ppubs_search_patents(
            '"artificial intelligence patent prosecution agent"'
        )
        assert result["total"] == 0
        assert "auto_retry" in result
        assert result["auto_retry"]["query_used"] == (
            "artificial AND intelligence AND patent AND prosecution AND agent"
        )
        assert result["auto_retry"]["total"] == 42
        assert mock_client.ppubs_search_patents.call_count == 2

    @pytest.mark.asyncio
    async def test_search_zero_without_phrase_gives_hint(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 0,
            "totalResults": 0,
            "page": 0,
            "perPage": 10,
            "totalPages": 0,
            "patents": [],
        }
        result = await src.server.ppubs_search_patents("zzznonexistentterm")
        assert result["total"] == 0
        assert "query_hint" in result
        assert "auto_retry" not in result
        assert mock_client.ppubs_search_patents.call_count == 1

    @pytest.mark.asyncio
    async def test_search_nonzero_no_hint_no_retry(self, mock_client):
        mock_client.ppubs_search_patents.return_value = {
            "numFound": 5,
            "totalResults": 5,
            "page": 0,
            "perPage": 10,
            "totalPages": 1,
            "patents": [],
        }
        result = await src.server.ppubs_search_patents("graphene battery")
        assert "query_hint" not in result
        assert "auto_retry" not in result

    @pytest.mark.asyncio
    async def test_count_zero_with_phrase_triggers_auto_retry(self, mock_client):
        mock_client.ppubs_count_patents.side_effect = [
            {"numResults": 0, "q": '"AI agent"', "databaseFilters": []},
            {
                "numResults": 1346,
                "q": "AI AND agent",
                "databaseFilters": [
                    {"databaseName": "US-PGPUB", "countryCodes": []},
                    {"databaseName": "USPAT", "countryCodes": []},
                    {"databaseName": "USOCR", "countryCodes": []},
                ],
            },
        ]
        result = await src.server.ppubs_get_search_count('"AI agent"')
        assert result["total"] == 0
        assert "auto_retry" in result
        assert result["auto_retry"]["query_used"] == "AI AND agent"
        assert result["auto_retry"]["total"] == 1346
        assert result["auto_retry"]["sources"] == ["US-PGPUB", "USPAT", "USOCR"]
        assert mock_client.ppubs_count_patents.call_count == 2

    @pytest.mark.asyncio
    async def test_count_zero_without_phrase_gives_hint(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 0,
            "q": "zzznonexistent",
            "databaseFilters": [],
        }
        result = await src.server.ppubs_get_search_count("zzznonexistent")
        assert result["total"] == 0
        assert "query_hint" in result
        assert "auto_retry" not in result
        assert mock_client.ppubs_count_patents.call_count == 1

    @pytest.mark.asyncio
    async def test_count_nonzero_no_hint_no_retry(self, mock_client):
        mock_client.ppubs_count_patents.return_value = {
            "numResults": 53254,
            "q": "graphene AND battery",
            "databaseFilters": [{"databaseName": "USPAT", "countryCodes": []}],
        }
        result = await src.server.ppubs_get_search_count("graphene battery")
        assert "query_hint" not in result
        assert "auto_retry" not in result


class TestPublicationNumberNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("6103599", "6103599"),
            ("6,103,599", "6103599"),
            ("US 6,103,599", "6103599"),
            ("US-6103599", "6103599"),
            ("US-6103599-A", "6103599"),
            ("US-20260121151-A1", "20260121151"),
            ("US-20260126277-A1", "20260126277"),
            ("US 2026/0126277", "2026/0126277"),  # slash form unmodified
            ("20260121151", "20260121151"),
            ("US-1234567-B2", "1234567"),
            ("US-7000000-E", "7000000"),
            ("US-PP12345-P3", "PP12345"),  # plant patent
            ("  US-6103599-A  ", "6103599"),  # whitespace
        ],
    )
    def test_normalize(self, raw, expected):
        assert UsptoClient._normalize_publication_number(raw) == expected


class TestRateLimitParsing:
    def test_parse_retry_after_uspto_header(self):
        resp = httpx.Response(429, headers={"x-rate-limit-retry-after-seconds": "10"})
        # Adds 1s buffer past the server's stated delay
        assert UsptoClient._parse_retry_after(resp) == 11

    def test_parse_retry_after_standard_header(self):
        resp = httpx.Response(429, headers={"retry-after": "5"})
        assert UsptoClient._parse_retry_after(resp) == 6

    def test_parse_retry_after_uspto_takes_precedence(self):
        resp = httpx.Response(
            429,
            headers={
                "x-rate-limit-retry-after-seconds": "10",
                "retry-after": "5",
            },
        )
        assert UsptoClient._parse_retry_after(resp) == 11

    def test_parse_retry_after_default_when_no_header(self):
        resp = httpx.Response(429)
        assert UsptoClient._parse_retry_after(resp) == 30

    def test_parse_retry_after_default_when_unparseable(self):
        resp = httpx.Response(429, headers={"retry-after": "soon-ish"})
        assert UsptoClient._parse_retry_after(resp) == 30

    def test_parse_retry_after_default_when_zero(self):
        resp = httpx.Response(429, headers={"x-rate-limit-retry-after-seconds": "0"})
        assert UsptoClient._parse_retry_after(resp) == 30

    def test_parse_retry_after_caps_at_5_minutes(self):
        resp = httpx.Response(429, headers={"x-rate-limit-retry-after-seconds": "9999"})
        assert UsptoClient._parse_retry_after(resp) == 300


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


class TestFindPatentsBy:
    @pytest.mark.asyncio
    async def test_assignee_query_envelope(self, mock_client):
        mock_client.find_patents_by.return_value = {
            "numFound": 5,
            "totalResults": 5,
            "page": 0,
            "perPage": 10,
            "totalPages": 1,
            "patents": [
                {
                    "guid": "US-1234567-B2",
                    "type": "USPAT",
                    "kindCode": ["B2"],
                    "publicationReferenceDocumentNumber": "1234567",
                    "inventionTitle": "Widget",
                    "datePublished": "2020-01-01T00:00:00Z",
                    "applicationNumber": "10/000001",
                    "inventorsShort": "Doe; Jane et al.",
                    "applicantName": ["Doe; Jane"],
                    "assigneeName": ["IBM"],
                    "mainClassificationCode": "2/2",
                    "ipcCodeFlattened": "G06F1/00",
                    "cpcInventiveFlattened": "G06F1/00",
                    "score": 1.0,
                }
            ],
        }
        result = await src.server.find_patents_by(assignee="IBM")
        assert result["total"] == 5
        assert len(result["results"]) == 1
        assert result["results"][0]["assigneeName"] == ["IBM"]
        mock_client.find_patents_by.assert_called_once_with(
            inventor=None,
            assignee="IBM",
            cpc_class=None,
            year_from=None,
            year_to=None,
            limit=10,
            sort="date_publ desc",
            sources=None,
        )

    @pytest.mark.asyncio
    async def test_no_params_returns_error_without_client_call(self, mock_client):
        result = await src.server.find_patents_by()
        assert "error" in result
        mock_client.find_patents_by.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_param_passthrough(self, mock_client):
        mock_client.find_patents_by.return_value = {
            "numFound": 2,
            "totalResults": 2,
            "page": 0,
            "perPage": 10,
            "totalPages": 1,
            "patents": [],
        }
        result = await src.server.find_patents_by(
            inventor="Smith", year_from=2020, year_to=2023, limit=5
        )
        assert result["total"] == 2
        mock_client.find_patents_by.assert_called_once_with(
            inventor="Smith",
            assignee=None,
            cpc_class=None,
            year_from=2020,
            year_to=2023,
            limit=5,
            sort="date_publ desc",
            sources=None,
        )

    @pytest.mark.asyncio
    async def test_verbosity_minimal_strips_noise(self, mock_client):
        mock_client.find_patents_by.return_value = {
            "numFound": 1,
            "totalResults": 1,
            "page": 0,
            "perPage": 10,
            "totalPages": 1,
            "patents": [
                {
                    "guid": "US-1-A1",
                    "type": "US-PGPUB",
                    "kindCode": ["A1"],
                    "publicationReferenceDocumentNumber": "1",
                    "inventionTitle": "T",
                    "datePublished": "2024-01-01T00:00:00Z",
                    "applicationNumber": "00/0",
                    "applicantName": ["X"],
                    "assigneeName": [],
                    "mainClassificationCode": "1",
                    "ipcCodeFlattened": "A",
                    "cpcInventiveFlattened": "A",
                    "frontPageStart": 1,
                }
            ],
        }
        result = await src.server.find_patents_by(assignee="X", verbosity="minimal")
        record = result["results"][0]
        assert "frontPageStart" not in record
        assert "applicationNumber" not in record
        assert "guid" in record
        assert "inventionTitle" in record


class TestComparePatentLandscape:
    @pytest.mark.asyncio
    async def test_basic_two_topic_comparison(self, mock_client):
        mock_client.compare_patent_landscape.return_value = {
            "comparisons": [
                {"topic": "graphene battery", "query_used": "graphene AND battery", "total": 53254},
                {
                    "topic": "solid state battery",
                    "query_used": "solid AND state AND battery",
                    "total": 12000,
                },
            ],
            "sources": ["US-PGPUB", "USPAT", "USOCR"],
        }
        result = await src.server.compare_patent_landscape(
            topics=["graphene battery", "solid state battery"]
        )
        assert len(result["comparisons"]) == 2
        assert result["comparisons"][0]["total"] == 53254
        assert result["comparisons"][1]["total"] == 12000
        assert result["sources"] == ["US-PGPUB", "USPAT", "USOCR"]
        mock_client.compare_patent_landscape.assert_called_once_with(
            topics=["graphene battery", "solid state battery"]
        )

    @pytest.mark.asyncio
    async def test_single_topic_returns_error(self, mock_client):
        result = await src.server.compare_patent_landscape(topics=["graphene battery"])
        assert "error" in result
        mock_client.compare_patent_landscape.assert_not_called()

    @pytest.mark.asyncio
    async def test_eight_topics_returns_error(self, mock_client):
        result = await src.server.compare_patent_landscape(
            topics=["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]
        )
        assert "error" in result
        mock_client.compare_patent_landscape.assert_not_called()

    @pytest.mark.asyncio
    async def test_seven_topics_allowed(self, mock_client):
        mock_client.compare_patent_landscape.return_value = {
            "comparisons": [
                {"topic": f"t{i}", "query_used": f"t{i}", "total": i * 100} for i in range(1, 8)
            ],
            "sources": ["US-PGPUB", "USPAT", "USOCR"],
        }
        result = await src.server.compare_patent_landscape(
            topics=["t1", "t2", "t3", "t4", "t5", "t6", "t7"]
        )
        assert "error" not in result
        assert len(result["comparisons"]) == 7
        mock_client.compare_patent_landscape.assert_called_once()
