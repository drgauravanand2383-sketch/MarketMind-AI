"""PennyStockEligibilityProvider — the per-market eligibility gate.

One config-driven implementation (`ConfigurableEligibilityProvider`)
serves all four `PennyStockMarket`s, each given its own
`PennyStockEligibilityCriteria` instance — this satisfies "each market
must have a market-specific eligibility profile" without four
near-duplicate classes differing only in threshold values. A market
whose rules genuinely diverge *structurally* (not just by threshold —
e.g. a check no other market needs at all) can still get its own
`PennyStockEligibilityProvider` implementation later without changing
this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.global_markets.eligibility.models import EligibilityCheckResult, PennyStockEligibilityCriteria
from app.global_markets.models import NormalizedAssetSnapshot

__all__ = ["PennyStockEligibilityProvider", "ConfigurableEligibilityProvider"]


class PennyStockEligibilityProvider(ABC):
    """Abstract contract every penny/micro-cap eligibility gate must satisfy."""

    @abstractmethod
    def evaluate(self, snapshot: NormalizedAssetSnapshot) -> EligibilityCheckResult:
        raise NotImplementedError


class ConfigurableEligibilityProvider(PennyStockEligibilityProvider):
    """Evaluates a `NormalizedAssetSnapshot` against one
    `PennyStockEligibilityCriteria`.

    Every configured (non-`None`) threshold that the snapshot has real
    data for is checked; a threshold the snapshot has no data for is
    counted toward `data_completeness_ratio` but never silently treated
    as a pass or a fail — a genuinely missing field is missing data, not
    evidence either way.
    """

    def __init__(self, criteria: PennyStockEligibilityCriteria) -> None:
        self._criteria = criteria

    def evaluate(self, snapshot: NormalizedAssetSnapshot) -> EligibilityCheckResult:
        criteria = self._criteria
        reasons: list[str] = []
        total = 0
        evaluated = 0

        def check_max(value: float | None, threshold: float | None, label: str) -> None:
            nonlocal total, evaluated
            if threshold is None:
                return
            total += 1
            if value is None:
                return
            evaluated += 1
            if value > threshold:
                reasons.append(f"{label} {value} exceeds max {threshold}")

        def check_min(value: float | None, threshold: float | None, label: str) -> None:
            nonlocal total, evaluated
            if threshold is None:
                return
            total += 1
            if value is None:
                return
            evaluated += 1
            if value < threshold:
                reasons.append(f"{label} {value} below min {threshold}")

        if criteria.exclude_suspended:
            total += 1
            evaluated += 1
            if snapshot.is_suspended:
                reasons.append("suspended")
        if criteria.exclude_delisted:
            total += 1
            evaluated += 1
            if snapshot.is_delisted:
                reasons.append("delisted")

        check_max(snapshot.price, criteria.max_price, "price")
        check_min(snapshot.market_cap, criteria.min_market_cap, "market_cap")
        check_max(snapshot.market_cap, criteria.max_market_cap, "market_cap")
        check_min(
            snapshot.avg_daily_traded_value, criteria.min_avg_daily_traded_value, "avg_daily_traded_value"
        )
        check_min(snapshot.avg_daily_volume, criteria.min_daily_volume, "avg_daily_volume")
        check_max(snapshot.bid_ask_spread_percent, criteria.max_spread_percent, "bid_ask_spread_percent")

        if criteria.min_trading_history_days > 0:
            total += 1
            if snapshot.trading_history_days is not None:
                evaluated += 1
                if snapshot.trading_history_days < criteria.min_trading_history_days:
                    reasons.append(
                        f"trading_history_days {snapshot.trading_history_days} "
                        f"below min {criteria.min_trading_history_days}"
                    )

        if criteria.max_volume_to_market_cap_ratio is not None:
            total += 1
            if snapshot.avg_daily_volume is not None and snapshot.market_cap:
                evaluated += 1
                ratio = snapshot.avg_daily_volume / snapshot.market_cap
                if ratio > criteria.max_volume_to_market_cap_ratio:
                    reasons.append(
                        f"volume_to_market_cap_ratio {ratio:.4f} "
                        f"exceeds max {criteria.max_volume_to_market_cap_ratio}"
                    )

        completeness = (evaluated / total) if total > 0 else 1.0
        if completeness < criteria.min_data_completeness_ratio:
            reasons.append(
                f"data completeness {completeness:.2f} below required "
                f"{criteria.min_data_completeness_ratio:.2f}"
            )

        return EligibilityCheckResult(
            ticker=snapshot.ticker,
            market=criteria.market,
            eligible=not reasons,
            failed_reasons=tuple(reasons),
            data_completeness_ratio=round(completeness, 4),
        )
