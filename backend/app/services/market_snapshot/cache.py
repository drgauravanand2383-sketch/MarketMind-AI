"""In-memory, TTL-bounded cache for MarketSnapshots (Milestone 13).

Not a distributed/Redis cache — no existing infrastructure in this
codebase requires one for this purpose (the same "don't invent
distributed infrastructure the architecture doesn't call for" judgment
already applied to `InMemoryResultStore`/`InMemoryMetricsRecorder`
elsewhere). Process-local, lost on restart — acceptable for a bounded,
short-TTL quote cache; a real distributed cache is a documented future
option, not a gap this milestone silently papers over (see
`docs/architecture/MARKET_DATA_ARCHITECTURE.md` §6).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.market_snapshot.models import MarketSnapshot

__all__ = ["InMemoryMarketSnapshotCache"]


class InMemoryMarketSnapshotCache:
    """Caches one MarketSnapshot per entity_id, with a bounded TTL.

    Deterministic cache key: `entity_id` (the canonical, stable
    identifier) — never the display name, and never the ticker alone
    (two different entities could theoretically share a ticker string
    across exchanges; `entity_id` cannot collide that way).
    """

    def __init__(self, ttl_seconds: float) -> None:
        """Initialize the cache.

        Args:
            ttl_seconds: How long a cached snapshot is considered fresh.
                Must be positive.
        """
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0; got {ttl_seconds!r}.")
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, MarketSnapshot] = {}

    def put(self, snapshot: MarketSnapshot) -> None:
        """Store `snapshot`, keyed by its own `entity_id`."""
        self._store[snapshot.entity_id] = snapshot

    def get(self, entity_id: str) -> MarketSnapshot | None:
        """Return the cached snapshot for `entity_id`, regardless of
        freshness — use `is_fresh()` to classify it. `None` if nothing
        has ever been cached for this entity."""
        return self._store.get(entity_id)

    def is_fresh(self, snapshot: MarketSnapshot, *, now: datetime | None = None) -> bool:
        """Whether `snapshot` is still within this cache's freshness window.

        Compares against `snapshot.fetched_at` (when *this service*
        cached it), never `quoted_at` (the provider's own timestamp,
        which can legitimately be older than `fetched_at` even for a
        freshly-fetched quote — e.g. a quote fetched after market close
        still carries the last trade's own timestamp).
        """
        current_time = now or datetime.now(UTC)
        age_seconds = (current_time - snapshot.fetched_at).total_seconds()
        return age_seconds < self._ttl_seconds

    def clear(self) -> None:
        """Remove every cached snapshot — for tests/administrative reset."""
        self._store.clear()
