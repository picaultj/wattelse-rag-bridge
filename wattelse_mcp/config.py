"""Configuration for the WattElse <-> MCP bridge, sourced from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings are read from `WATTELSE_*` environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_prefix="WATTELSE_", env_file=".env", extra="ignore")

    base_url: str = "https://localhost:1978"
    client_id: str = "wattelse"
    client_secret: str
    verify_ssl: bool = True
    request_timeout: float = 60.0

    default_group_id: str = "default"
    default_config: str = "default_config"

    mcp_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
