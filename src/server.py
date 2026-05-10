"""USPTO MCP server — wraps PPUBS (Phase 1) and ODP (Phase 2) data sources."""

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from src.config import mask_credential, settings
from src.uspto_client import PPUBS_DEFAULT_SOURCES, UsptoClient

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ── Response field filtering ──

RESPONSE_FIELDS: dict[str, dict[str, Optional[list[str]]]] = {
    # patent_summary covers per-record shape from POST /api/searches/
    # searchWithBeFamily (89 raw fields per record).
    #
    # Tier rules:
    #  minimal — disambiguating ID line: guid/type/kindCode + pub# + title
    #            + date. 6 fields. Fits one display row.
    #  standard — patent-attorney triage view: + appl#/dates, key persons
    #            (inventorsShort/applicantName/assigneeName), modern + legacy
    #            classification (CPC/IPC/USPC flattened only), family ID,
    #            primaryExaminer, search relevance score. 18 fields.
    #            Excludes: KWIC highlights, *Highlights duplicates, pf*
    #            preferred-publication variants, image/Solr internals,
    #            Derwent indexing.
    #  full —    no filter (89 fields). Use for debugging or rare access
    #            to PCT/Hague/foreign-citation/sequence/biological data.
    #
    # Field-naming gotchas:
    #  - inventorsShort: "Doe; Jane et al." compact string. Often empty for
    #    US-PGPUB (inventor data populates fully at grant).
    #  - assigneeName: list. Empty pre-grant on US-PGPUB; use applicantName
    #    for application-time owner.
    #  - kindCode: list, e.g. ["A1"] (PGPUB), ["B2"] (granted), ["A"]
    #    (older grant), ["E"] (reissue).
    #  - publicationReferenceDocumentNumber appears in 3 forms in the raw
    #    response (canonical, "1", "One"); we surface the canonical.
    "patent_summary": {
        "minimal": [
            "guid",
            "type",
            "kindCode",
            "publicationReferenceDocumentNumber",
            "inventionTitle",
            "datePublished",
        ],
        "standard": [
            # ID
            "guid",
            "type",
            "kindCode",
            "publicationReferenceDocumentNumber",
            "applicationNumber",
            # Title + dates
            "inventionTitle",
            "datePublished",
            "applicationFilingDate",
            # People
            "inventorsShort",
            "applicantName",
            "assigneeName",
            # Classification (modern + legacy)
            "mainClassificationCode",
            "ipcCodeFlattened",
            "cpcInventiveFlattened",
            "cpcAdditionalFlattened",
            # Family
            "familyIdentifierCur",
            # Examiner (often null on US-PGPUB; populates at examination)
            "primaryExaminer",
            # Search relevance
            "score",
        ],
        "full": None,
    },
    # patent_detail covers GET /api/patents/highlight/{guid} (450 raw
    # fields top-level — 5× the search response).
    #
    # Tier rules:
    #  minimal — disambiguating ID + lead inventor + abstract HTML.
    #            8 fields. Suitable for quick "what is this patent?"
    #            answers without dumping claims.
    #  standard — full patent-attorney record: ID, dates, all people
    #            (inventors short+full, applicant, assignee with location),
    #            modern + legacy classification (flattened only), family
    #            + continuity, examiners, legal firm, counts (claims/
    #            drawings/figures), abstract + claims HTML, page-range
    #            pointers for the four useful sections (abstract / claims
    #            / spec / drawings). 37 fields.
    #            Excludes: KWIC highlights, the 8 niche page pointers
    #            (amend/bib/cert*/frontPage/ptab/searchReport/supplemental),
    #            sub-heading HTML M0-M6, full per-inventor address arrays,
    #            applicant address arrays, raw classification lists when
    #            *Flattened says it concisely, Derwent / PCT / Hague /
    #            foreign-citation metadata.
    #  full —    no filter (450 fields).
    #
    # Field-naming gotchas:
    #  - inventorsName: list of full names — detail-only.
    #  - inventorsShort: compact display — detail + summary.
    #  - legalFirmName: typically populated; attorneyName / principal-
    #    AttorneyName are often null even on granted patents.
    #  - continuityData: free-text on granted, structured chain on PGPUB.
    #  - numberOfClaims/Drawings/Figures: null on PGPUB, populated on
    #    granted (assigned at examination).
    #  - familyIdentifierCur: int (older patents) or 13-digit int
    #    (newer applications).
    "patent_detail": {
        "minimal": [
            "guid",
            "type",
            "kindCode",
            "inventionTitle",
            "datePublished",
            "applicationNumber",
            "inventorsShort",
            "abstractHtml",
        ],
        "standard": [
            # ID
            "guid",
            "type",
            "kindCode",
            "inventionTitle",
            "datePublished",
            "applicationNumber",
            "applicationFilingDate",
            # People — full + compact + concise location
            "inventorsShort",
            "inventorsName",
            "applicantName",
            "assigneeName",
            "assigneeCity",
            "assigneeState",
            "assigneeCountry",
            # Classification (modern + legacy + USPC, flattened only)
            "mainClassificationCode",
            "ipcCodeFlattened",
            "cpcInventiveFlattened",
            "cpcAdditionalFlattened",
            # Family + continuity
            "familyIdentifierCur",
            "continuityData",
            # Examiners + legal firm
            "primaryExaminer",
            "assistantExaminer",
            "legalFirmName",
            "attorneyName",
            # Counts (concise scalar metadata)
            "numberOfClaims",
            "numberOfDrawingSheets",
            "numberOfFigures",
            # Heavy text (the two patent-attorneys actually read)
            "abstractHtml",
            "claimsHtml",
            # Page-range pointers — 4 useful sections only (PDF assembly)
            "abstractStart",
            "abstractEnd",
            "claimsStart",
            "claimsEnd",
            "specificationStart",
            "specificationEnd",
            "drawingsStart",
            "drawingsEnd",
        ],
        "full": None,
    },
}

VALID_VERBOSITY_LEVELS = {"minimal", "standard", "full"}


def _filter_response(response: Any, resource_type: str, verbosity: str = "standard") -> Any:
    """Filter response fields based on verbosity level."""
    if response is None:
        return None

    if verbosity not in VALID_VERBOSITY_LEVELS:
        logger.warning(f"Invalid verbosity '{verbosity}', using 'standard'")
        verbosity = "standard"

    if verbosity == "full":
        return response

    if resource_type not in RESPONSE_FIELDS:
        return response

    fields = RESPONSE_FIELDS[resource_type].get(verbosity)
    if fields is None:
        return response

    field_set = set(fields)

    def filter_dict(d: dict) -> dict:
        return {k: v for k, v in d.items() if k in field_set}

    if isinstance(response, list):
        return [filter_dict(item) for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        return filter_dict(response)
    return response


# ── Client accessor ──

_client: Optional[UsptoClient] = None


def _get_client() -> UsptoClient:
    """Get the global USPTO client instance."""
    if _client is None:
        raise RuntimeError("USPTO client not initialized. Ensure server lifespan has run.")
    return _client


# ── Server lifecycle ──


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Initialize USPTO client on startup, cleanup on shutdown."""
    global _client

    odp_key_value: Optional[str] = None
    if settings.has_odp_api_key:
        odp_key_value = settings.get_odp_api_key_value()
        logger.info(
            "ODP key present (key: %s); Phase 2 ODP tools will load when added.",
            mask_credential(odp_key_value),
        )
    else:
        logger.info("USPTO_ODP_API_KEY not set — Phase 1 only (PPUBS, no auth).")

    logger.info(
        "Connecting to USPTO data sources (PPUBS=%s, ODP=%s)",
        settings.ppubs_url,
        settings.odp_url,
    )

    client = UsptoClient(
        ppubs_url=settings.ppubs_url,
        odp_url=settings.odp_url,
        odp_api_key=odp_key_value,
    )

    connected = await client.check_connection()
    if connected:
        logger.info("PPUBS reachability verified.")
    else:
        logger.warning("Could not verify PPUBS reachability. Tools may fail.")

    _client = client

    try:
        yield
    finally:
        logger.info("Shutting down USPTO MCP server...")
        await client.close()
        _client = None


# ── MCP Server ──

_mcp_port_str = os.environ.get("MCP_PORT", "8000")
try:
    _mcp_port = int(_mcp_port_str)
except ValueError:
    _mcp_port = 8000

mcp = FastMCP(
    "USPTO MCP",
    lifespan=server_lifespan,
    host=os.environ.get("MCP_HOST", "127.0.0.1"),
    port=_mcp_port,
)


# ── Tools ──


@mcp.tool(
    "check_ppubs_status",
    description=(
        "Probe USPTO Patent Public Search (ppubs.uspto.gov) for reachability. "
        "No auth required. Returns reachability flag, HTTP status code, and "
        "the configured base URL. Useful as a smoke test from the gateway."
    ),
)
async def check_ppubs_status() -> dict:
    """Foundation-slice tool — verifies PPUBS reachability."""
    client = _get_client()
    return await client.check_ppubs_status()


@mcp.tool(
    "ppubs_search_patents",
    description=(
        "Full-text search of US granted patents and published applications via "
        "USPTO Patent Public Search (ppubs.uspto.gov). No auth required. "
        "Query syntax follows PPUBS BRS — e.g. 'graphene', 'graphene AND "
        "battery', '(\"6103599\").pn.'. **CRITICAL — BRS defaults to OR** "
        "between space-separated terms: 'graphene battery' matches ANY "
        "patent mentioning EITHER word (~2.4M results in 2026), NOT both. "
        "For intersection, use explicit 'graphene AND battery' (~53k); for "
        "exact-phrase matching, double-quote: '\"graphene battery\"'. When a "
        "user gives a plain English multi-word topic ('graphene battery', "
        "'CRISPR gene editing', 'quantum dot displays'), rewrite to AND form "
        "before calling: 'graphene AND battery', etc. Default sources: "
        "US-PGPUB (published applications), USPAT (granted patents), USOCR "
        "(OCR'd older patents). Returns a paginated envelope of summary-tier "
        "records (id, title, applicant, classification, dates, family ID — "
        "about 18 fields per record at standard verbosity). NOTE: the "
        "summary tier does NOT include abstract or claims HTML. To get a "
        "full document with abstract+claims+full applicant/assignee+inventor "
        "metadata, follow up with `ppubs_get_patent_by_number(publication_"
        "number=<record.publicationReferenceDocumentNumber>)` for any result "
        "you want to drill into. Alternatively pass verbosity='full' to this "
        "search tool to include all 89 raw PPUBS fields per record at once "
        "(heavier response, useful for batch analysis)."
    ),
)
async def ppubs_search_patents(
    query: str,
    limit: int = 10,
    start: int = 0,
    sort: str = "date_publ desc",
    sources: Optional[list[str]] = None,
    verbosity: str = "standard",
) -> dict:
    """Search PPUBS and return a paginated, verbosity-filtered result envelope."""
    client = _get_client()
    payload = await client.ppubs_search_patents(
        query=query,
        limit=limit,
        start=start,
        sort=sort,
        sources=sources,
    )
    patents = payload.get("patents") or []
    return {
        "total": payload.get("totalResults"),
        "num_found": payload.get("numFound"),
        "page": payload.get("page"),
        "per_page": payload.get("perPage"),
        "total_pages": payload.get("totalPages"),
        "results": _filter_response(patents, "patent_summary", verbosity),
    }


@mcp.tool(
    "ppubs_get_patent_by_number",
    description=(
        "Fetch the FULL document for a single US patent or published "
        "application from USPTO Patent Public Search (ppubs.uspto.gov). Use "
        "this AFTER `ppubs_search_patents` returns a result you want to drill "
        "into — search results are summary-tier and do NOT include the "
        "abstract or claims, but THIS tool returns the full document with "
        "**abstractHtml**, **claimsHtml**, full per-inventor names + per-"
        "assignee metadata + locations, full classification (CPC/IPC/USPC "
        "flattened), continuity data, examiners, legal firm, and family "
        "identifier. Accepts the bare pub# (e.g. '6103599' for granted, "
        "'20260126277' for published applications) AND the GUID-shaped form "
        "returned in search results' `guid` field (e.g. 'US-6103599-A', "
        "'US-20260121151-A1') — kind-code suffix is stripped automatically. "
        "Also tolerates commas/whitespace/'US ' prefix. To call this tool, "
        "you can pass either `record.publicationReferenceDocumentNumber` or "
        "`record.guid` from a `ppubs_search_patents` result. Returns "
        "{found: false} if no match. No auth required."
    ),
)
async def ppubs_get_patent_by_number(
    publication_number: str,
    verbosity: str = "standard",
) -> dict:
    """Fetch a single PPUBS document by publication number, verbosity-filtered."""
    client = _get_client()
    detail = await client.ppubs_get_patent_by_number(publication_number)
    if detail is None:
        return {
            "found": False,
            "publication_number": publication_number,
        }
    return {
        "found": True,
        "publication_number": publication_number,
        "record": _filter_response(detail, "patent_detail", verbosity),
    }


@mcp.tool(
    "ppubs_get_search_count",
    description=(
        "Count US patents and published applications matching a PPUBS BRS "
        "query without fetching any documents. Cheaper and faster than "
        "`ppubs_search_patents` — useful for tuning a query before running "
        "the full search, or for answering 'how many?' questions directly. "
        "**CRITICAL — BRS defaults to OR** between space-separated terms: "
        "'graphene battery' matches ANY patent mentioning EITHER word (~2.4M "
        "results), NOT both. For intersection, use 'graphene AND battery' "
        "(~53k). For exact phrase, double-quote: '\"graphene battery\"'. When "
        "the user gives a plain multi-word topic, rewrite to AND form first. "
        "Default sources: US-PGPUB, USPAT, USOCR. Returns {total, query, "
        "sources}. After this, call `ppubs_search_patents` to list records."
    ),
)
async def ppubs_get_search_count(
    query: str,
    sources: Optional[list[str]] = None,
) -> dict:
    """Get count for a PPUBS query (no document pagination)."""
    client = _get_client()
    payload = await client.ppubs_count_patents(query=query, sources=sources)
    echoed = [
        f.get("databaseName")
        for f in (payload.get("databaseFilters") or [])
        if f.get("databaseName")
    ]
    return {
        "total": payload.get("numResults"),
        "query": payload.get("q") or query,
        "sources": echoed or list(PPUBS_DEFAULT_SOURCES),
    }


# ── Transport resolution ──

VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")


def _resolve_transport(argv: list[str] | None = None, env: dict[str, str] | None = None) -> str:
    """Determine transport from CLI flags or env var."""
    if argv is None:
        argv = sys.argv
    if env is None:
        env = dict(os.environ)

    if "--sse" in argv:
        return "sse"
    if "--streamable-http" in argv:
        return "streamable-http"

    env_transport = env.get("USPTO_TRANSPORT", "").lower()
    if env_transport in VALID_TRANSPORTS:
        return env_transport
    return "stdio"


def _run(transport: str) -> None:
    """Dispatch to the right runner. Wraps HTTP transports with bearer auth
    when ``MCP_BEARER_TOKEN`` is set; stdio is always passed through untouched.
    """
    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    import uvicorn

    from src.auth import BearerAuthMiddleware
    from src.logging_filters import StandaloneSseWriterRaceFilter

    sdk_logger = logging.getLogger("mcp.server.streamable_http")
    if not any(isinstance(f, StandaloneSseWriterRaceFilter) for f in sdk_logger.filters):
        sdk_logger.addFilter(StandaloneSseWriterRaceFilter())

    app = mcp.streamable_http_app() if transport == "streamable-http" else mcp.sse_app()

    if settings.has_bearer_token:
        app = BearerAuthMiddleware(app, expected_token=settings.get_bearer_token_value())
        logger.info("Bearer-token middleware enabled for %s transport", transport)
    else:
        logger.warning(
            "MCP_BEARER_TOKEN not set — %s transport accepts unauthenticated requests",
            transport,
        )

    config = uvicorn.Config(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    uvicorn.Server(config).run()


if __name__ == "__main__":
    transport = _resolve_transport()
    logger.info(f"Starting USPTO MCP server with {transport} transport")
    _run(transport)
