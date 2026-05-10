"""USPTO data-source client.

Phase 1 covers PPUBS (Patent Public Search) at ``ppubs.uspto.gov`` — no auth,
full-text search of granted US patents and published applications. Phase 2
will add ODP (Open Data Portal) endpoints behind ``USPTO_ODP_API_KEY``.

PPUBS protocol notes (locked 2026-05-10 against live probe):

* The wire API lives under ``/api/`` and is reverse-engineered from the
  ``/pubwebapp/`` SPA. Each request needs three correlated bits of
  authentication state:
    - cookies seeded by ``GET /pubwebapp/``,
    - a ``caseId`` integer returned in the body of
      ``POST /api/users/me/session`` (request body literal: integer ``-1``),
    - an ``X-Access-Token`` header value also returned by that endpoint.
* Sessions time out at 1800 s (per the session response's
  ``sessionTimeOutTime``). We cache the session for 25 min and re-establish
  on first 403 (no exponential retry — a single re-auth covers the common
  expiry case).
* Search uses two endpoints in sequence: ``POST /api/searches/counts``
  returns a count and a term graph; ``POST /api/searches/searchWithBeFamily``
  returns the actual records. For Phase 1's ``search_patents`` we go
  straight to ``searchWithBeFamily`` since the response payload already
  includes ``numFound``/``totalResults`` — the counts call is only useful
  when the operator wants the count without the records.
* Default sources are the three PPUBS databases: ``US-PGPUB`` (published
  applications), ``USPAT`` (granted patents), ``USOCR`` (OCR'd older
  patents).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

PPUBS_USER_AGENT = "tetra-uspto-mcp/1.0"
PPUBS_SESSION_TTL = timedelta(minutes=25)
PPUBS_DEFAULT_SOURCES = ("US-PGPUB", "USPAT", "USOCR")


class UsptoAPIError(Exception):
    """Raised when a USPTO data source returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class UsptoClient:
    """Async client for USPTO data sources.

    Holds two httpx clients — one for PPUBS (no auth) and one for ODP (key
    required, only constructed when ``odp_api_key`` is provided). Phase 1
    only uses the PPUBS client.
    """

    def __init__(
        self,
        ppubs_url: str,
        odp_url: str = "https://api.uspto.gov",
        odp_api_key: Optional[str] = None,
    ):
        self.ppubs_url = ppubs_url.rstrip("/")
        self.odp_url = odp_url.rstrip("/")
        self._odp_api_key = odp_api_key

        # PPUBS expects cookies + Origin/Referer pinned to /pubwebapp/.
        self._ppubs = httpx.AsyncClient(
            base_url=self.ppubs_url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": PPUBS_USER_AGENT,
                "Origin": self.ppubs_url,
                "Referer": f"{self.ppubs_url}/pubwebapp/",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self._ppubs_case_id: Optional[int] = None
        self._ppubs_token: Optional[str] = None
        self._ppubs_session_expires_at: Optional[datetime] = None

        self._odp: Optional[httpx.AsyncClient] = None
        if odp_api_key:
            self._odp = httpx.AsyncClient(
                base_url=self.odp_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": PPUBS_USER_AGENT,
                    "X-API-KEY": odp_api_key,
                },
                timeout=30.0,
            )

    async def close(self) -> None:
        """Close the underlying httpx clients."""
        await self._ppubs.aclose()
        if self._odp is not None:
            await self._odp.aclose()

    @property
    def has_odp(self) -> bool:
        """True iff an ODP API key was provided at construction."""
        return self._odp is not None

    # ── PPUBS session ──

    async def _establish_ppubs_session(self) -> None:
        """Open a fresh PPUBS session.

        Resets cookie jar, hits ``/pubwebapp/`` to seed cookies, then POSTs
        ``-1`` to ``/api/users/me/session`` to obtain ``caseId`` and
        ``X-Access-Token``. Stores both for use by subsequent search calls.
        """
        self._ppubs.cookies = httpx.Cookies()

        await self._ppubs.get("/pubwebapp/")

        response = await self._ppubs.post(
            "/api/users/me/session",
            json=-1,
            headers={"X-Access-Token": "null"},
        )
        if response.status_code != 200:
            raise UsptoAPIError(
                f"PPUBS session creation failed: {response.text[:200]}",
                status_code=response.status_code,
            )

        body = response.json()
        try:
            self._ppubs_case_id = int(body["userCase"]["caseId"])
        except (KeyError, TypeError, ValueError) as exc:
            raise UsptoAPIError(
                f"PPUBS session response missing userCase.caseId: {body!r}"
            ) from exc

        token = response.headers.get("x-access-token") or response.headers.get("X-Access-Token")
        if not token:
            raise UsptoAPIError("PPUBS session response missing X-Access-Token header")
        self._ppubs_token = token
        self._ppubs.headers["X-Access-Token"] = token
        self._ppubs_session_expires_at = datetime.now() + PPUBS_SESSION_TTL
        logger.info("PPUBS session established (caseId=%s)", self._ppubs_case_id)

    async def _ensure_ppubs_session(self) -> None:
        """Establish or reuse a cached PPUBS session."""
        if (
            self._ppubs_case_id is not None
            and self._ppubs_session_expires_at is not None
            and datetime.now() < self._ppubs_session_expires_at
        ):
            return
        await self._establish_ppubs_session()

    async def _ppubs_post(self, path: str, json_body: Any) -> httpx.Response:
        """POST to a PPUBS endpoint with one auto-retry on session expiry.

        Reauthenticates and retries once on 403; everything else is returned
        as-is for the caller to interpret.
        """
        response = await self._ppubs.post(path, json=json_body)
        if response.status_code == 403:
            logger.info("PPUBS returned 403 — re-establishing session and retrying once")
            await self._establish_ppubs_session()
            response = await self._ppubs.post(path, json=json_body)
        return response

    # ── PPUBS reachability ──

    async def check_ppubs_status(self) -> dict:
        """Probe PPUBS root to confirm reachability.

        Foundation-slice tool: confirms the wrapper can reach
        ``ppubs.uspto.gov`` without an API key. Returns a dict suitable for
        gateway smoke tests; never raises on transport errors so the MCP
        client gets a structured failure rather than an exception.
        """
        try:
            response = await self._ppubs.get("/")
            return {
                "reachable": True,
                "status_code": response.status_code,
                "url": self.ppubs_url,
            }
        except httpx.HTTPError as exc:
            logger.warning("PPUBS reachability probe failed: %s", exc)
            return {
                "reachable": False,
                "status_code": None,
                "url": self.ppubs_url,
                "error": str(exc),
            }

    async def check_connection(self) -> bool:
        """Verify USPTO data-source connectivity by probing PPUBS."""
        result = await self.check_ppubs_status()
        return bool(result.get("reachable"))

    # ── PPUBS search ──

    async def ppubs_search_patents(
        self,
        query: str,
        *,
        limit: int = 10,
        start: int = 0,
        sort: str = "date_publ desc",
        sources: Optional[list[str]] = None,
        plurals: bool = True,
        british_equivalents: bool = True,
        default_operator: str = "OR",
    ) -> dict:
        """Run a PPUBS search and return the parsed response.

        Returns the raw PPUBS payload — top-level keys include ``patents``
        (list of result records), ``numFound``, ``totalResults``, ``page``,
        ``perPage``, ``totalPages``. The server layer is responsible for
        verbosity-filtering the per-record fields.
        """
        await self._ensure_ppubs_session()

        if sources is None:
            sources = list(PPUBS_DEFAULT_SOURCES)

        query_block = {
            "caseId": self._ppubs_case_id,
            "hl_snippets": "2",
            "op": default_operator,
            "q": query,
            "queryName": query,
            "highlights": "1",
            "qt": "brs",
            "spellCheck": False,
            "viewName": "tile",
            "plurals": plurals,
            "britishEquivalents": british_equivalents,
            "databaseFilters": [{"databaseName": s, "countryCodes": []} for s in sources],
            "searchType": 1,
            "ignorePersist": True,
            "userEnteredQuery": query,
        }
        body = {
            "start": start,
            "pageCount": min(max(limit, 1), 500),
            "sort": sort,
            "docFamilyFiltering": "familyIdFiltering",
            "searchType": 1,
            "familyIdEnglishOnly": True,
            "familyIdFirstPreferred": "US-PGPUB",
            "familyIdSecondPreferred": "USPAT",
            "familyIdThirdPreferred": "FPRS",
            "showDocPerFamilyPref": "showEnglish",
            "queryId": 0,
            "tagDocSearch": False,
            "query": query_block,
        }

        response = await self._ppubs_post("/api/searches/searchWithBeFamily", body)
        if response.status_code != 200:
            raise UsptoAPIError(
                f"PPUBS search failed: {response.text[:200]}",
                status_code=response.status_code,
            )
        return response.json()

    @staticmethod
    def _normalize_publication_number(value: str) -> str:
        """Strip commas, whitespace, and an optional leading 'US' from a publication number."""
        cleaned = str(value).replace(",", "").strip()
        if cleaned.upper().startswith("US"):
            cleaned = cleaned[2:].lstrip(" -")
        return cleaned

    async def ppubs_get_patent_by_number(self, publication_number: str) -> Optional[dict]:
        """Look up a single PPUBS document by publication number.

        Two-call flow: BRS-search ``("<pn>").pn.`` to resolve the GUID + type,
        then GET ``/api/patents/highlight/{guid}?source=<type>`` for the full
        document. Returns the raw highlight payload (a deep dict with
        abstract/claims HTML, classification, applicant/assignee metadata,
        family identifiers, page-range pointers) or ``None`` if the search
        finds no match.

        ``.pn.`` works for both granted patents (USPAT) and published
        applications (US-PGPUB) — verified live 2026-05-10.
        """
        await self._ensure_ppubs_session()

        pn = self._normalize_publication_number(publication_number)
        brs = f'("{pn}").pn.'

        # Step 1 — BRS search for the publication number.
        search_payload = await self.ppubs_search_patents(query=brs, limit=1)
        patents = search_payload.get("patents") or []
        if not patents:
            return None

        record = patents[0]
        guid = record.get("guid")
        source_type = record.get("type")
        if not guid or not source_type:
            raise UsptoAPIError(f"PPUBS search returned a record without guid/type: {record!r}")

        # Step 2 — fetch full document detail. Endpoint is GET, not POST,
        # so the shared _ppubs_post 403-retry helper doesn't apply.
        params = {"queryId": 1, "source": source_type, "includeSections": "true"}
        path = f"/api/patents/highlight/{guid}"
        response = await self._ppubs.get(path, params=params)
        if response.status_code == 403:
            logger.info("PPUBS highlight returned 403 — re-establishing session and retrying")
            await self._establish_ppubs_session()
            response = await self._ppubs.get(path, params=params)
        if response.status_code != 200:
            raise UsptoAPIError(
                f"PPUBS highlight fetch failed: {response.text[:200]}",
                status_code=response.status_code,
            )
        return response.json()
