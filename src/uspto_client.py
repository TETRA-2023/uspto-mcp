"""USPTO data-source client.

Phase 1 covers PPUBS (Patent Public Search) — no auth, full-text search of
granted US patents and published applications. Phase 2 will add ODP
(Open Data Portal) endpoints behind ``USPTO_ODP_API_KEY``.

This scaffold ships with one foundation-slice operation
(:meth:`UsptoClient.check_ppubs_status`) that proves wiring end-to-end.
PPUBS endpoint signatures (search, get-by-number) are locked in subsequent
``feat:`` commits against probed live responses, so the scaffold does not
guess them.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


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

        self._ppubs = httpx.AsyncClient(
            base_url=self.ppubs_url,
            headers={"Accept": "application/json", "User-Agent": "tetra-uspto-mcp/0.1"},
            timeout=30.0,
        )

        self._odp: Optional[httpx.AsyncClient] = None
        if odp_api_key:
            self._odp = httpx.AsyncClient(
                base_url=self.odp_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "tetra-uspto-mcp/0.1",
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
