# uspto-mcp

MCP server wrapping USPTO patent data sources for the Model Context Protocol.

- **Phase 1 (current)**: PPUBS — Patent Public Search at `ppubs.uspto.gov`. No authentication, full-text search of granted US patents and published applications.
- **Phase 2 (deferred)**: ODP — Open Data Portal at `api.uspto.gov`. Adds assignment records, examination data, file-wrapper history, and real-time application status. Requires an ODP API key (procurement gated by USPTO MyUSPTO + ID.me identity verification — see Taiga US #947).

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- For Phase 2 only: a USPTO ODP API key from `data.uspto.gov/apis/getting-started`

### Installation

```bash
git clone https://github.com/TETRA-2023/uspto-mcp.git
cd uspto-mcp
uv sync
```

### Configuration

```bash
cp .env.example .env
# Phase 1: no edits needed — PPUBS works out of the box.
# Phase 2: set USPTO_ODP_API_KEY when the procurement unblocks.
```

| Variable | Description | Default |
|----------|-------------|---------|
| `USPTO_PPUBS_URL` | PPUBS base URL | `https://ppubs.uspto.gov` |
| `USPTO_ODP_URL` | ODP base URL (Phase 2) | `https://api.uspto.gov` |
| `USPTO_ODP_API_KEY` | ODP API key (Phase 2 only) | *unset* |
| `USPTO_TRANSPORT` | Transport mode (`stdio`, `sse`, `streamable-http`) | `stdio` |
| `MCP_HOST` | Bind address for HTTP transports | `127.0.0.1` |
| `MCP_PORT` | Listen port for HTTP transports | `8000` |
| `MCP_BEARER_TOKEN` | Optional bearer token enforced on HTTP transports (no-op for stdio) | *unset* |

## Usage

### stdio (Claude Code / local)

```bash
uv run python src/server.py
```

### streamable-http (Docker / remote)

```bash
uv run python src/server.py --streamable-http
```

### Docker

```bash
docker build -t uspto-mcp .
docker run --env-file .env uspto-mcp --streamable-http
```

### Behind an HTTP gateway

When fronting the wrapper with a gateway (LiteLLM, Kong, NGINX), set
`MCP_BEARER_TOKEN` to a random secret. The wrapper will then reject any HTTP
request that does not present a matching `Authorization: Bearer <token>`
header.

```bash
export MCP_BEARER_TOKEN="$(openssl rand -hex 32)"
export USPTO_TRANSPORT=streamable-http
export MCP_HOST=0.0.0.0
uv run python src/server.py
```

## Tools

### Foundation

| Tool | Description |
|------|-------------|
| `check_ppubs_status` | Probe PPUBS reachability — returns `{reachable, status_code, url}`. No auth. |

### PPUBS (Phase 1, in development)

To be added in subsequent commits as endpoints are locked against live PPUBS responses:

| Tool | Description |
|------|-------------|
| `ppubs_search_patents` | Full-text search across granted US patents + published applications. |
| `ppubs_get_patent_by_number` | Fetch one record by publication number. |

### ODP (Phase 2, deferred)

Loaded only when `USPTO_ODP_API_KEY` is set:

| Tool | Description |
|------|-------------|
| `odp_search_applications` | Structured search via ODP. |
| `odp_get_application` | Full ODP application record. |
| `odp_get_continuity` | Continuation / divisional chain. |
| `odp_get_transactions` | Prosecution-history events. |
| `odp_get_assignment` | Chain-of-title. |

All query tools support a `verbosity` parameter: `minimal`, `standard` (default), or `full`.

## Development

```bash
# Install dev dependencies
uv sync --all-extras --dev

# Run tests
uv run pytest tests/test_server.py -v

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Pre-commit hooks
uv run pre-commit install
```

## License

MIT
