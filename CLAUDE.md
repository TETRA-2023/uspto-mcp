# CLAUDE.md — uspto-mcp

## Project Overview

MCP server wrapping USPTO patent data sources. Built on FastMCP with httpx.

- **Package**: `uspto-mcp`
- **Python**: >= 3.12
- **Registry**: `ghcr.io/tetra-2023/uspto-mcp`
- **Phase 1**: PPUBS (Patent Public Search) — no auth, ships independently of USPTO procurement.
- **Phase 2 (deferred)**: ODP (Open Data Portal) — requires API key, gated on MyUSPTO + ID.me unblock. Tracked in Taiga US #947.

## Architecture

```
src/
  server.py            — MCP tool definitions (FastMCP @mcp.tool() wrappers)
  uspto_client.py      — UsptoClient: async httpx, two-track (PPUBS no-auth + ODP key-required)
  config.py            — Pydantic settings: USPTO_PPUBS_URL, USPTO_ODP_URL, USPTO_ODP_API_KEY, MCP_BEARER_TOKEN
  auth.py              — BearerAuthMiddleware for HTTP transports
  logging_filters.py   — StandaloneSseWriterRaceFilter (mute benign upstream noise)
```

- `server.py` registers tools and wires the client lifespan.
- `uspto_client.py` holds two httpx clients side-by-side; the ODP client is constructed only when `USPTO_ODP_API_KEY` is set, so Phase 1 deployments don't need any credentials.
- `_filter_response` provides minimal/standard/full verbosity routing (mirrors homarr-mcp pattern); fields registered per resource type in `RESPONSE_FIELDS`.

## Endpoint locking

Phase 1 tool signatures (`ppubs_search_patents`, `ppubs_get_patent_by_number`) are not yet implemented. They are added per-commit as endpoints are locked against probed live PPUBS responses or by porting from `riemannzeta/patent_mcp_server` (MIT). Do not guess endpoint paths or request shapes — probe first.

## Development Setup

```bash
uv sync --all-extras --dev
cp .env.example .env  # Phase 1 needs no edits
```

## Running

```bash
uv run python src/server.py                    # stdio (default)
uv run python src/server.py --streamable-http  # HTTP transport
```

Environment variables: `USPTO_PPUBS_URL`, `USPTO_ODP_URL`, `USPTO_ODP_API_KEY`, `USPTO_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_BEARER_TOKEN`.

## Testing

```bash
uv run pytest tests/test_server.py -v
```

## Code Conventions

- **Linter/formatter**: ruff (line-length=100, target py312, rules: E, F, W, I)
- **Commit messages**: Conventional Commits (`feat:`, `fix:`, `chore:`, etc.)
- **Tool pattern**: `@mcp.tool()` → get client → call client method → filter response
- **Response filtering**: `verbosity` parameter (minimal/standard/full) via `RESPONSE_FIELDS` dict
- **Security**: Never log API keys. Use `SecretStr` for credentials. ODP key only needed for Phase 2 tools.
- **Phase 1 PPUBS endpoints**: lock against probed responses; no guessing.
