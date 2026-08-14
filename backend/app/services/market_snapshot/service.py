"""Market Snapshot Service (Milestone 13).

`MarketSnapshotService` is the single place any caller (Research, the
market-data refresh workflow, the operational trigger) goes to get a
normalized market snapshot for a canonical entity. It isolates every
other part of the system from provider calls entirely — Research,
Portfolio logic, Risk analytics, and the UI never construct or call a
`MarketDataProvider` directly.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.market_data.models import MarketQuote
from app.providers.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.market_data.provider import MarketDataProvider
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.market_snapshot.cache import InMemoryMarketSnapshotCache
from app.services.market_snapshot.models import (
    MarketSnapshot,
    MarketSnapshotResult,
    MarketSnapshotStatus,
)

__all__ = ["MarketSnapshotService"]

_logger = logging.getLogger("marketmind.services.market_snapshot")

DEFAULT_MAX_CONCURRENCY = 5


class MarketSnapshotService:
    """Obtains a normalized, cached, freshness-aware market snapshot for
    a canonical entity — the single integration point between the
    Milestone 12 entity model and the Milestone 13 market-data provider."""

    def __init__(
        self,
        provider: MarketDataProvider,
        entity_resolver: EntityResolutionService | None,
        cache: InMemoryMarketSnapshotCache,
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        """Initialize the service.

        Args:
            provider: The MarketDataProvider to fetch quotes from.
            entity_resolver: Resolves an entity_id to its
                ticker/exchange/currency. `None` is accepted (mirrors
                every other optional collaborator in this codebase's own
                bootstrap conventions) — every lookup then reports
                `ENTITY_NOT_MAPPED`, never raises.
            cache: The TTL-bounded snapshot cache.
            max_concurrency: Bounds in-flight provider requests during
                `get_snapshots()` — an accidental-request-storm guard
                (§8), not a measured vendor rate limit.
        """
        self._provider = provider
        self._entity_resolver = entity_resolver
        self._cache = cache
        self._max_concurrency = max_concurrency

    async def get_snapshot(self, entity_id: str, *, use_cache: bool = True) -> MarketSnapshotResult:
        """Get a normalized market snapshot for one canonical entity.

        Never raises for an ordinary outcome — every case (unmapped
        entity, provider failure of any kind, no data, a still-fresh or
        now-stale cached value) is represented explicitly in the
        returned `MarketSnapshotResult.status`.
        """
        reference = self._resolve_entity(entity_id)
        if reference is None:
            return MarketSnapshotResult(
                entity_id=entity_id,
                status=MarketSnapshotStatus.ENTITY_NOT_MAPPED,
                reason=f"No canonical entity found for id {entity_id!r}.",
            )
        if not reference.ticker:
            name = reference.canonical_name
            reason = f"{name!r} has no known ticker — cannot look up market data."
            return MarketSnapshotResult(
                entity_id=entity_id, status=MarketSnapshotStatus.ENTITY_NOT_MAPPED, reason=reason
            )

        cached = self._cache.get(entity_id)
        if use_cache and cached is not None and self._cache.is_fresh(cached):
            return MarketSnapshotResult(
                entity_id=entity_id,
                status=MarketSnapshotStatus.FRESH,
                snapshot=cached,
                reason="Served from cache, within the freshness window.",
            )

        try:
            quote = await self._provider.get_quote(reference.ticker)
        except ProviderTimeoutError as exc:
            status = MarketSnapshotStatus.PROVIDER_TIMEOUT
            return self._failure_result(entity_id, cached, status, exc)
        except ProviderRateLimitError as exc:
            status = MarketSnapshotStatus.RATE_LIMITED
            return self._failure_result(entity_id, cached, status, exc)
        except ProviderNoDataError as exc:
            status = MarketSnapshotStatus.NO_DATA
            return self._failure_result(entity_id, cached, status, exc)
        except ProviderResponseError as exc:
            status = MarketSnapshotStatus.INVALID_RESPONSE
            return self._failure_result(entity_id, cached, status, exc)
        except ProviderConnectionError as exc:
            status = MarketSnapshotStatus.PROVIDER_UNAVAILABLE
            return self._failure_result(entity_id, cached, status, exc)
        except ProviderError as exc:
            status = MarketSnapshotStatus.UNAVAILABLE
            return self._failure_result(entity_id, cached, status, exc)

        snapshot = self._build_snapshot(reference, quote)
        self._cache.put(snapshot)
        return MarketSnapshotResult(
            entity_id=entity_id,
            status=MarketSnapshotStatus.FRESH,
            snapshot=snapshot,
            reason=f"Fetched live from {snapshot.provider}.",
        )

    async def get_snapshots(
        self, entity_ids: list[str], *, use_cache: bool = True
    ) -> list[MarketSnapshotResult]:
        """Get market snapshots for multiple entities, concurrently.

        Requirements this satisfies (§12): duplicate entity ids are
        requested only once; concurrency is bounded
        (`max_concurrency`); one entity's failure never prevents any
        other entity's result — `get_snapshot()` itself never raises for
        an ordinary failure, and any genuinely unexpected exception is
        still caught here and converted into an `UNAVAILABLE` result
        rather than aborting the whole batch.
        """
        deduplicated = list(dict.fromkeys(entity_ids))
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _bounded(entity_id: str) -> MarketSnapshotResult:
            async with semaphore:
                return await self.get_snapshot(entity_id, use_cache=use_cache)

        results = await asyncio.gather(
            *(_bounded(entity_id) for entity_id in deduplicated), return_exceptions=True
        )

        final: list[MarketSnapshotResult] = []
        for entity_id, result in zip(deduplicated, results, strict=True):
            if isinstance(result, BaseException):
                _logger.warning(
                    "market_snapshot_unexpected_error",
                    extra={"entity_id": entity_id, "error": str(result)},
                )
                final.append(
                    MarketSnapshotResult(
                        entity_id=entity_id,
                        status=MarketSnapshotStatus.UNAVAILABLE,
                        reason=f"Unexpected error: {result}",
                    )
                )
            else:
                final.append(result)
        return final

    def _resolve_entity(self, entity_id: str) -> CompanyReference | None:
        if self._entity_resolver is None:
            return None
        return self._entity_resolver.get_by_entity_id(entity_id)

    def _failure_result(
        self,
        entity_id: str,
        cached: MarketSnapshot | None,
        status: MarketSnapshotStatus,
        exc: Exception,
    ) -> MarketSnapshotResult:
        """Build the result for a provider failure — serving a stale
        cached value (explicitly marked STALE, never silently presented
        as fresh) when one exists, or the specific failure status
        otherwise.
        """
        _logger.warning(
            "market_snapshot_provider_failed",
            extra={"entity_id": entity_id, "status": status.value, "error": str(exc)},
        )
        if cached is not None:
            fetched_at = cached.fetched_at.isoformat()
            reason = f"Provider failed ({exc}); serving cached data fetched at {fetched_at}."
            return MarketSnapshotResult(
                entity_id=entity_id,
                status=MarketSnapshotStatus.STALE,
                snapshot=cached,
                reason=reason,
            )
        return MarketSnapshotResult(entity_id=entity_id, status=status, reason=str(exc))

    def _build_snapshot(self, reference: CompanyReference, quote: MarketQuote) -> MarketSnapshot:
        return MarketSnapshot(
            entity_id=reference.entity_id,
            canonical_name=reference.canonical_name,
            ticker=quote.ticker,
            exchange=quote.exchange,
            currency=quote.currency,
            price=quote.price,
            previous_close=quote.previous_close,
            change=quote.change,
            change_percent=quote.change_percent,
            day_high=quote.day_high,
            day_low=quote.day_low,
            volume=quote.volume,
            quoted_at=quote.timestamp,
            fetched_at=datetime.now(UTC),
            provider=self._provider.provider_name(),
        )
