import os

import pytest

from wattelse_mcp.config import get_settings


@pytest.fixture(autouse=True)
def _wattelse_env(monkeypatch):
    """Ensure required settings are present and get_settings() picks up per-test overrides."""
    monkeypatch.setenv("WATTELSE_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WATTELSE_BASE_URL", "https://wattelse.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
