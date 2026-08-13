"""Shared fixtures for CompositeKnowledgeRepository tests.

Wraps a REAL PostgresKnowledgeRepository (backed by in-memory SQLite via
aiosqlite) and a REAL ChromaKnowledgeRepository (backed by the fake
in-memory ChromaDB collection already built for Sprint 15's own test
suite, reused here rather than duplicated) — the composite is tested
against genuine repository implementations, not hand-rolled doubles of
its own dependencies, so its routing/coordination logic is exercised for
real.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository
from app.repositories.knowledge.postgres.models import Base
from app.repositories.knowledge.postgres.repository import PostgresKnowledgeRepository
from tests.repositories.knowledge.chroma.test_repository import _FakeChromaCollection


@pytest.fixture
async def postgres_repository() -> AsyncIterator[PostgresKnowledgeRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PostgresKnowledgeRepository(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
def chroma_repository() -> ChromaKnowledgeRepository:
    return ChromaKnowledgeRepository(_FakeChromaCollection())


@pytest.fixture
def composite_repository(
    postgres_repository: PostgresKnowledgeRepository,
    chroma_repository: ChromaKnowledgeRepository,
) -> CompositeKnowledgeRepository:
    return CompositeKnowledgeRepository(postgres_repository, chroma_repository)
