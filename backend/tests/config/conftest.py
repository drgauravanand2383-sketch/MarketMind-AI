"""Test isolation for the Configuration Service.

Every test in this package runs against a cleared environment: whatever
the developer's shell or a real local `.env` happens to contain must never
leak into an assertion. Each `*Settings` class is constructed with
`_env_file=None` so a real `.env` on disk (if one exists) is never read
either — these tests exercise pydantic-settings' env-var and default
handling in isolation, not this machine's actual configuration.
"""

from __future__ import annotations

import pytest

_ENV_VARS_TO_CLEAR = [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "DATABASE_URL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "REDIS_URL",
    "CHROMA_HOST",
    "CHROMA_PORT",
    "CHROMA_PERSIST_DIRECTORY",
    "CHROMA_COLLECTION_NAME",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_MAX_TOKENS",
    "ANTHROPIC_TEMPERATURE",
    "ANTHROPIC_TIMEOUT",
    "EMBEDDING_PROVIDER_ID",
    "EMBEDDING_MODEL",
    "EMBEDDING_TIMEOUT_SECONDS",
    "EMBEDDING_MAX_RETRIES",
    "EMBEDDING_RETRY_BACKOFF_SECONDS",
    "RSS_FEED_URLS",
    "RSS_USER_AGENT",
    "LOG_LEVEL",
    "LOGGING_LEVEL",
    "LLM_PROVIDER",
    "SCHEDULER_ENABLED",
    "SCHEDULER_DEFAULT_INTERVAL_SECONDS",
    "API_HOST",
    "API_PORT",
    "API_V1_PREFIX",
    "ALLOWED_ORIGINS",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(key, raising=False)
