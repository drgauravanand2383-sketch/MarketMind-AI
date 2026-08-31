"""MarketSessionResolutionService — builds the `MarketSessionContext`
bundle for one `MarketRegion`.

This is the one place downstream stages (performance calculation,
eligibility, ranking, the workflow) read calendar facts from. Per
approved Decision 1's architectural rule, this service is always called
once *independently per market region* — it never assumes two regions
share a trading date, and it never itself iterates "all markets" (the
workflow does that, calling this once per region).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.global_markets.calendar.registry import TradingCalendarRegistry
from app.global_markets.models import DataFreshnessStatus, MarketRegion, MarketSessionContext

__all__ = ["MarketSessionResolutionService", "MARKET_REGION_TIMEZONES"]

MARKET_REGION_TIMEZONES: dict[MarketRegion, str] = {
    MarketRegion.INDIA: "Asia/Kolkata",
    MarketRegion.US: "America/New_York",
    MarketRegion.CHINA: "Asia/Shanghai",
    # Crypto and Forex have no single "home" exchange timezone — both are
    # reported in UTC, the timezone every `TradingCalendarProvider`
    # implementation for these two regions is itself anchored to (see
    # `app.global_markets.calendar.continuous_calendar`).
    MarketRegion.CRYPTO: "UTC",
    MarketRegion.FOREX: "UTC",
}

_DEFAULT_STALE_AFTER = timedelta(hours=24)
"""How long past a market's last completed session close a *later fetch
stage's* own retrieved data may still be presented as `PREVIOUS_CLOSE`
before that stage should mark it `STALE` instead — see
`MarketSessionContext.freshness_cutoff`'s own docstring. This resolver
itself never applies this threshold to its own `data_freshness_status`
(a market closed for an ordinary weekend, or a long holiday cluster, is
correctly `PREVIOUS_CLOSE` no matter how many wall-clock hours have
elapsed since its last close — see `resolve()`'s own comment)."""


class MarketSessionResolutionService:
    """Resolves one `MarketRegion`'s full calendar/freshness context, on demand."""

    def __init__(
        self,
        calendar_registry: TradingCalendarRegistry,
        *,
        stale_after: timedelta = _DEFAULT_STALE_AFTER,
    ) -> None:
        self._calendar_registry = calendar_registry
        self._stale_after = stale_after

    def resolve(self, market_region: MarketRegion, as_of: datetime | None = None) -> MarketSessionContext:
        """Build the `MarketSessionContext` for `market_region`.

        Args:
            market_region: Which market's calendar to resolve.
            as_of: The instant to evaluate "is it open now"/"what's the
                latest session" against. Defaults to the current time
                (UTC) — tests always pass an explicit value so results
                are deterministic and reproducible.

        Raises:
            UnsupportedMarketRegionError: If `market_region` has no
                registered `TradingCalendarProvider` (propagated from
                `TradingCalendarRegistry.get`).
        """
        as_of = as_of if as_of is not None else datetime.now(UTC)
        retrieved_at = datetime.now(UTC)
        calendar = self._calendar_registry.get(market_region)

        is_trading_now = calendar.is_open_at(as_of)
        local_today = calendar.local_date(as_of)
        is_holiday = calendar.is_holiday(local_today)
        session_date = calendar.current_or_last_session_date(as_of)
        last_completed = calendar.last_completed_session(as_of)

        # This resolver only ever determines LIVE / PREVIOUS_CLOSE /
        # UNAVAILABLE — a calendar alone can always tell those three
        # apart with certainty. STALE cannot be determined here: an
        # ordinary weekend (or a long holiday cluster, e.g. Chinese New
        # Year) already puts `as_of` well past the last session's own
        # close, without any actual data being stale at all — the last
        # completed session genuinely *is* the correct, current
        # "previous close" regardless of how many wall-clock hours have
        # elapsed. STALE only becomes meaningful once real fetched data
        # exists to compare against `freshness_cutoff` below — a later
        # phase's `DataProvenance.data_freshness_status` (per-datapoint,
        # computed by comparing that value's own `retrieved_at`/
        # `source_timestamp` against this cutoff), never this
        # calendar-only context.
        if is_trading_now:
            freshness_status = DataFreshnessStatus.LIVE
            freshness_cutoff = None
        elif last_completed is not None:
            freshness_status = DataFreshnessStatus.PREVIOUS_CLOSE
            freshness_cutoff = last_completed.close_at + self._stale_after
        else:
            freshness_status = DataFreshnessStatus.UNAVAILABLE
            freshness_cutoff = None

        return MarketSessionContext(
            market_region=market_region,
            market_timezone=MARKET_REGION_TIMEZONES[market_region],
            retrieved_at=retrieved_at,
            as_of_timestamp=as_of,
            is_trading_now=is_trading_now,
            is_holiday=is_holiday,
            market_session_date=session_date,
            last_completed_session=last_completed,
            data_freshness_status=freshness_status,
            freshness_cutoff=freshness_cutoff,
        )
