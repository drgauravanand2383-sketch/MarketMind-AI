"""Schemas for the Market Snapshot Service (Milestone 13).

`MarketSnapshotResult` is what every caller (Research, the refresh
workflow, the operational trigger) actually receives — always, whether
data was obtained or not. It never raises for an ordinary "no data" or
"provider failed" outcome; those are represented explicitly via `status`,
never conflated with each other and never silently turned into a
fabricated zero/null business value.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.market_data.models import Currency, Exchange

__all__ = ["MarketSnapshotStatus", "MarketSnapshot", "MarketSnapshotResult"]


class MarketSnapshotStatus(str, Enum):
    """Every distinct outcome `MarketSnapshotService.get_snapshot()` can
    report — see `docs/architecture/MARKET_DATA_ARCHITECTURE.md` §7 for
    the full policy.

    FRESH: a quote was obtained (just now, or already cached within the
        freshness window) and `snapshot` is populated.
    STALE: the provider could not be reached/failed, but a previously
        cached quote exists past its freshness window — `snapshot` is
        still populated (with its original, unmodified provider
        timestamp), explicitly marked stale rather than presented as
        current.
    ENTITY_NOT_MAPPED: the entity has no known ticker in the canonical
        reference set — never guessed.
    PROVIDER_UNAVAILABLE: a connection-level failure (not a timeout).
    PROVIDER_TIMEOUT: the provider request exceeded its configured timeout.
    RATE_LIMITED: the provider rejected the request as rate-limited.
    INVALID_RESPONSE: the provider responded, but the response was
        malformed/unparseable.
    NO_DATA: the provider was reached and responded successfully, but has
        no data at all for this symbol (e.g. delisted/unknown ticker).
    UNAVAILABLE: a generic catch-all — no cached value exists and the
        failure doesn't fit any of the more specific categories above.
    """

    FRESH = "FRESH"
    STALE = "STALE"
    ENTITY_NOT_MAPPED = "ENTITY_NOT_MAPPED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NO_DATA = "NO_DATA"
    UNAVAILABLE = "UNAVAILABLE"


class MarketSnapshot(BaseModel):
    """A normalized market snapshot for one canonical entity.

    Deliberately distinct from `app.market_data.models.MarketQuote` (the
    raw provider-shaped normalized quote): this model additionally
    answers "which canonical entity," "which provider," "fetched when"
    (`fetched_at`, this service's own cache-write time) versus "quoted as
    of when" (`quoted_at`, the provider's own timestamp) — the exact
    distinction Milestone 13 §19 ("data quality") requires every
    displayed price be able to answer.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    canonical_name: str
    ticker: str
    exchange: Exchange | None = None
    currency: Currency | None = None
    price: float
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    quoted_at: datetime
    fetched_at: datetime
    provider: str
    trading_status: str | None = None


class MarketSnapshotResult(BaseModel):
    """The output of `MarketSnapshotService.get_snapshot()` — always
    returned, never raised, for any ordinary outcome (entity unmapped,
    provider failure, no data, stale cache). `snapshot` is populated only
    for `FRESH`/`STALE`."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    status: MarketSnapshotStatus
    snapshot: MarketSnapshot | None = None
    reason: str
