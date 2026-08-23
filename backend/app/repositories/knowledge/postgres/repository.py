"""SQLAlchemy async ORM implementation of BaseKnowledgeRepository.

PostgresKnowledgeRepository persists RelationalRecords into PostgreSQL and
retrieves/searches/deletes through SQLAlchemy's async ORM. It contains no
business logic, generates no embeddings, and contains no ChromaDB code —
only translation between domain models and SQL operations, via the
mapper.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.knowledge.models import (
    DeleteResult,
    KnowledgeRecord,
    SaveResult,
    SearchQuery,
    SearchResult,
)
from app.repositories.knowledge.postgres.mapper import (
    model_to_knowledge_record,
    relational_record_to_model,
)
from app.repositories.knowledge.postgres.models import KnowledgeRecordModel
from app.repositories.knowledge.repository import BaseKnowledgeRepository
from app.services.embedding.models import EmbeddingBatch
from app.services.knowledge_ingestion.models import IngestionBatch

__all__ = ["PostgresKnowledgeRepository"]


class PostgresKnowledgeRepository(BaseKnowledgeRepository):
    """Persists and retrieves knowledge through an injected SQLAlchemy async session factory.

    Supported `SearchQuery.filters` keys:
        - "company": ILIKE match against title/summary. No dedicated
          company column exists on this table (RelationalRecord carries
          no company field) — this is a text match, the same limitation
          BaseKnowledgeRepository.search already has for every backend.
        - "provider": exact match against `source_provider_id`.
        - "source": exact match against the resolved `source` column.
        - "start_date" / "end_date": `datetime` bounds on `published_at_parsed`.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the repository.

        Args:
            session_factory: A SQLAlchemy `async_sessionmaker` this
                repository opens sessions from, injected by the caller.
                This repository never constructs its own engine or
                connection.
        """
        self._session_factory = session_factory

    async def save_batch(
        self, ingestion_batch: IngestionBatch, embedding_batch: EmbeddingBatch
    ) -> SaveResult:
        """Persist `ingestion_batch.relational_records` into PostgreSQL.

        `embedding_batch` is accepted to satisfy the BaseKnowledgeRepository
        contract but is not used: this repository stores relational data
        only and generates no embeddings. `vector_documents` are not
        handled here — this repository is PostgreSQL-only. Records are
        upserted (by primary key), so re-saving an already-known record_id
        updates it rather than failing.
        """
        records = ingestion_batch.relational_records
        errors: list[str] = []

        if records:
            try:
                async with self._session_factory() as session:
                    for record in records:
                        await session.merge(relational_record_to_model(record))
                    await session.commit()
            except Exception as exc:  # noqa: BLE001 - surfaced in SaveResult, not raised
                errors.append(str(exc))

        return SaveResult(
            batch_id=ingestion_batch.ingestion_metadata.batch_id,
            saved_at=datetime.now(UTC),
            vector_count=0,
            relational_count=0 if errors else len(records),
            success=not errors,
            errors=errors,
        )

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search by company/provider/source (text or exact match) and/or date range."""
        async with self._session_factory() as session:
            stmt = self._build_search_statement(query)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            SearchResult(id=row.id, score=None, text=row.summary, metadata=row.source_metadata)
            for row in rows
        ]

    def _build_search_statement(self, query: SearchQuery) -> Select[tuple[KnowledgeRecordModel]]:
        stmt = select(KnowledgeRecordModel)
        conditions = []

        if query.query_text:
            pattern = f"%{query.query_text}%"
            conditions.append(
                or_(
                    KnowledgeRecordModel.title.ilike(pattern),
                    KnowledgeRecordModel.summary.ilike(pattern),
                )
            )

        company = query.filters.get("company")
        if company:
            pattern = f"%{company}%"
            conditions.append(
                or_(
                    KnowledgeRecordModel.title.ilike(pattern),
                    KnowledgeRecordModel.summary.ilike(pattern),
                )
            )

        provider = query.filters.get("provider")
        if provider:
            conditions.append(KnowledgeRecordModel.source_provider_id == provider)

        source = query.filters.get("source")
        if source:
            conditions.append(KnowledgeRecordModel.source == source)

        start_date = query.filters.get("start_date")
        if start_date:
            conditions.append(KnowledgeRecordModel.published_at_parsed >= start_date)

        end_date = query.filters.get("end_date")
        if end_date:
            conditions.append(KnowledgeRecordModel.published_at_parsed <= end_date)

        for condition in conditions:
            stmt = stmt.where(condition)

        return stmt.limit(query.top_k)

    async def get(self, record_id: str) -> KnowledgeRecord | None:
        """Retrieve a single record by id."""
        async with self._session_factory() as session:
            model = await session.get(KnowledgeRecordModel, record_id)
        return model_to_knowledge_record(model) if model is not None else None

    async def delete(self, record_id: str) -> DeleteResult:
        """Delete a single record by id, reporting whether it existed."""
        async with self._session_factory() as session:
            model = await session.get(KnowledgeRecordModel, record_id)
            existed = model is not None
            if model is not None:
                await session.delete(model)
                await session.commit()
        return DeleteResult(id=record_id, deleted=existed)

    async def health_check(self) -> bool:
        """Report whether the database is reachable."""
        try:
            async with self._session_factory() as session:
                await session.execute(select(1))
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            return False
