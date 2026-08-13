"""Shared fixtures for `tests/performance` — mirrors
`tests/api/v1/conftest.py`'s `client` fixture exactly (same fast-fake-
repositories-override reasoning: without it, `/health` would block on an
unreachable real PostgreSQL server, making the benchmark measure network
timeouts instead of the endpoint's own overhead). Duplicated rather than
imported because `tests/performance` is a sibling package, not nested
under `tests/api/v1` — pytest fixture discovery via `conftest.py` only
reaches down a directory tree, never across siblings.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.api.v1.dependencies.state import REPOSITORY_NAMES, get_repositories_map
from app.main import create_app


class FakeHealthyRepository:
    async def health_check(self) -> bool:
        return True


def _fast_repositories_map(request: Request) -> dict[str, object]:
    return {name: FakeHealthyRepository() for name in REPOSITORY_NAMES}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_repositories_map] = _fast_repositories_map
    with TestClient(app) as test_client:
        yield test_client
