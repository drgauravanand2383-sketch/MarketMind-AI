"""Entity Resolution Backfill (Milestone 12).

`EntityResolutionBackfillService.run()` enriches already-ingested
knowledge records with entity resolution — the same computation
`KnowledgeIngestionService` performs for newly-ingested records, applied
retroactively to records that existed before entity resolution was
enabled, or before a given company was added to the reference set.

No article content is ever rewritten: only metadata is updated
(`ChromaKnowledgeRepository.update_metadata_batch`, which never touches
document text or embeddings). Idempotent by construction — resolution is
a pure function of a record's own text, so re-running this against
already-backfilled records recomputes and rewrites the exact same
outcome, not a different one.
"""

from __future__ import annotations

import logging
import time

from app.repositories.knowledge.chroma.repository import ChromaKnowledgeRepository
from app.repositories.knowledge.models import KnowledgeRecord
from app.services.entity_resolution.metadata import ENTITY_METADATA_KEYS, build_entity_metadata
from app.services.entity_resolution.models import (
    BackfillResult,
    ConfidenceTier,
    EntityResolutionContext,
    EntityResolutionResult,
)
from app.services.entity_resolution.service import EntityResolutionService

__all__ = ["EntityResolutionBackfillService"]

_logger = logging.getLogger("marketmind.services.entity_resolution.backfill")

DEFAULT_BATCH_SIZE = 100


class EntityResolutionBackfillService:
    """Resolves entities for already-ingested knowledge records, in place."""

    def __init__(
        self, repository: ChromaKnowledgeRepository, resolver: EntityResolutionService
    ) -> None:
        """Initialize the service.

        Args:
            repository: The ChromaDB-backed knowledge repository to read
                existing records from and write resolved metadata back to.
                Typed against the concrete `ChromaKnowledgeRepository`
                (not the abstract `BaseKnowledgeRepository`) because
                `list_all`/`update_metadata_batch` are Chroma-specific
                capabilities this milestone added — the only backend this
                deployment actually wires up (see `app/bootstrap.py`).
            resolver: The EntityResolutionService to resolve each record's
                text against — the same service (or an equivalently
                configured one) `KnowledgeIngestionService` uses, so a
                freshly-ingested record and a backfilled one are resolved
                identically.
        """
        self._repository = repository
        self._resolver = resolver

    async def run(
        self, *, batch_size: int = DEFAULT_BATCH_SIZE, dry_run: bool = False
    ) -> BackfillResult:
        """Resolve entities for every existing record, page by page.

        Args:
            batch_size: How many records to read (`list_all`) and, when
                not a dry run, write (`update_metadata_batch`) per page —
                bounds memory use so a large collection is never loaded
                entirely at once. Also the natural resumability unit: an
                operator who interrupts a run can rerun with the same
                `batch_size`, and since resolution is idempotent, already-
                processed records simply get recomputed to the same
                result rather than duplicated or corrupted.
            dry_run: When True, every record is resolved and counted, but
                `update_metadata_batch` is never called — nothing is
                written. Use this to preview a backfill's outcome first.

        Returns:
            A BackfillResult with per-tier counts and any per-page errors
            (a page that fails to update does not stop the remaining
            pages — errors are collected, not raised).
        """
        started = time.perf_counter()
        result = BackfillResult(dry_run=dry_run)
        offset = 0

        while True:
            page = await self._repository.list_all(limit=batch_size, offset=offset)
            if not page:
                break

            pending = self._process_page(page, result, dry_run=dry_run)
            if not dry_run:
                await self._write_page(pending, result)

            offset += len(page)
            if len(page) < batch_size:
                break

        result.duration_seconds = round(time.perf_counter() - started, 4)
        _logger.info(
            "entity_backfill_completed",
            extra={
                "dry_run": dry_run,
                "records_processed": result.records_processed,
                "records_updated": result.records_updated,
                "high_confidence_count": result.high_confidence_count,
                "medium_confidence_count": result.medium_confidence_count,
                "low_confidence_count": result.low_confidence_count,
                "unresolved_count": result.unresolved_count,
                "error_count": len(result.errors),
                "duration_seconds": result.duration_seconds,
            },
        )
        return result

    def _process_page(
        self, page: list[KnowledgeRecord], result: BackfillResult, *, dry_run: bool
    ) -> dict[str, dict[str, object]]:
        """Resolve every record in `page`, updating `result`'s counts.

        Returns each record's merged metadata, keyed by record id — empty
        when `dry_run` is True, since nothing needs to be written.
        """
        pending: dict[str, dict[str, object]] = {}
        for record in page:
            result.records_processed += 1
            resolution = self._resolver.resolve(
                record.text or "", EntityResolutionContext(title=record.title)
            )
            self._count_tier(resolution.confidence_tier, result)

            if not dry_run:
                pending[record.id] = self._merge_metadata(record, resolution)
        return pending

    async def _write_page(
        self, pending: dict[str, dict[str, object]], result: BackfillResult
    ) -> None:
        """Persist every record's merged metadata computed by `_process_page`."""
        if not pending:
            return
        ids = list(pending)
        try:
            await self._repository.update_metadata_batch(
                ids=ids, metadatas=[pending[record_id] for record_id in ids]
            )
            result.records_updated += len(ids)
        except Exception as exc:  # noqa: BLE001 - one bad page must not abort the whole backfill
            result.errors.append(str(exc))

    def _merge_metadata(
        self, record: KnowledgeRecord, resolution: EntityResolutionResult
    ) -> dict[str, object]:
        """Merge a fresh entity resolution onto `record`'s existing
        metadata, first stripping every previously-written entity field
        (`ENTITY_METADATA_KEYS`) so a record that no longer resolves to
        an entity doesn't keep a stale `entity_id` pointing at one."""
        preserved = {
            key: value for key, value in record.metadata.items() if key not in ENTITY_METADATA_KEYS
        }
        return {**preserved, **build_entity_metadata(resolution)}

    def _count_tier(self, tier: ConfidenceTier, result: BackfillResult) -> None:
        if tier == ConfidenceTier.HIGH:
            result.high_confidence_count += 1
        elif tier == ConfidenceTier.MEDIUM:
            result.medium_confidence_count += 1
        elif tier == ConfidenceTier.LOW:
            result.low_confidence_count += 1
        else:
            result.unresolved_count += 1
