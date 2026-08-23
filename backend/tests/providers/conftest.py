"""Shared fixtures for provider framework tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.providers.base import BaseProvider
from app.providers.models import ProviderConfig, ProviderResult


class StubProvider(BaseProvider):
    """A minimal, test-only concrete provider used to exercise BaseProvider/ProviderRegistry.

    Not a real provider implementation — RSS/NSE/BSE/etc. are out of scope
    for this framework sprint.
    """

    @property
    def provider_id(self) -> str:
        return "stub"

    @property
    def provider_name(self) -> str:
        return "Stub Provider"

    @property
    def version(self) -> str:
        return "0.1.0"

    async def fetch(self, **kwargs: object) -> ProviderResult:
        return ProviderResult(
            provider_id=self.provider_id,
            fetched_at=datetime.now(UTC),
            success=True,
            data={"echo": kwargs},
        )

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def stub_provider_class() -> type[BaseProvider]:
    return StubProvider


@pytest.fixture
def sample_config() -> ProviderConfig:
    return ProviderConfig(provider_id="stub", timeout=5.0)
