"""Configuration for the WattElse <-> MCP bridge, sourced from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """All settings are read from `WATTELSE_*` environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_prefix="WATTELSE_", env_file=_ENV_FILE, extra="ignore")

    base_url: str = "https://localhost:1978"
    client_id: str = "wattelse"
    client_token: str
    verify_ssl: bool | str = True
    request_timeout: float = 60.0

    default_group_id: str = "default"
    default_config: str = "default_config"

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000

    @field_validator("verify_ssl", mode="before")
    @classmethod
    def _coerce_verify_ssl(cls, v: object) -> object:
        # `verify_ssl` is bool | str (str = path to a custom CA bundle), but pydantic's union
        # resolution keeps env-var strings like "false"/"true" as-is instead of coercing them to
        # bool, which then makes httpx treat "false" as a (non-existent) CA bundle file path.
        if isinstance(v, str) and v.strip().lower() in {"true", "false", "1", "0", "yes", "no"}:
            return v.strip().lower() in {"true", "1", "yes"}
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
