"""Configuration management for USPTO MCP server."""

import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_FILE_PATH)


class UsptoSettings(BaseSettings):
    """USPTO MCP server settings.

    Phase 1 (PPUBS) needs no credentials. Phase 2 (ODP) requires
    ``USPTO_ODP_API_KEY`` once the MyUSPTO procurement unblocks; until then the
    Phase 2 tools are absent and the key field stays unset.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    ppubs_url: str = Field(
        default="https://ppubs.uspto.gov",
        alias="USPTO_PPUBS_URL",
        description="Patent Public Search base URL (no auth required)",
    )

    odp_url: str = Field(
        default="https://api.uspto.gov",
        alias="USPTO_ODP_URL",
        description="Open Data Portal base URL (Phase 2 — requires API key)",
    )

    odp_api_key: Optional[SecretStr] = Field(
        default=None,
        alias="USPTO_ODP_API_KEY",
        description="ODP API key for Phase 2 tools. Phase 1 (PPUBS) does not use this.",
    )

    bearer_token: Optional[SecretStr] = Field(
        default=None,
        alias="MCP_BEARER_TOKEN",
        description=(
            "Optional bearer token enforced on HTTP transports. When set, "
            "incoming streamable-http/sse requests must present "
            "'Authorization: Bearer <token>'. No-op for stdio transport."
        ),
    )

    @property
    def has_odp_api_key(self) -> bool:
        return self.odp_api_key is not None

    def get_odp_api_key_value(self) -> str:
        if self.odp_api_key is None:
            raise ValueError("USPTO_ODP_API_KEY is required for ODP tools but not set")
        return self.odp_api_key.get_secret_value()

    @property
    def has_bearer_token(self) -> bool:
        return self.bearer_token is not None

    def get_bearer_token_value(self) -> str:
        if self.bearer_token is None:
            raise ValueError("MCP_BEARER_TOKEN is not set")
        return self.bearer_token.get_secret_value()


def mask_credential(value: str, visible_chars: int = 2) -> str:
    """Mask a credential for safe logging."""
    if not value:
        return "<empty>"
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return (
        f"{value[:visible_chars]}{'*' * (len(value) - visible_chars * 2)}{value[-visible_chars:]}"
    )


settings = UsptoSettings()
