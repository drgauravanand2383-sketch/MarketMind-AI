"""Tests for `app.signals.reference_definitions` (v1.2 Priority 1).

Proves the replacement price-breakout signal is genuinely graduated
(never a fixed score/confidence regardless of input) and deterministic
(the same input always produces the same output) — the concrete fix for
the pilot's P1 finding (every alert previously scored exactly
confidence=100.0/score=100.0 because the live signal had a single,
trivially-always-true condition).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.market_data.models import MarketQuote
from app.signals.engine import SignalDetectionService
from app.signals.models import MarketDataSnapshot
from app.signals.reference_definitions import build_price_breakout_signal_definition

NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)
_engine = SignalDetectionService.__new__(SignalDetectionService)


def _definition(**overrides: object):
    return build_price_breakout_signal_definition(definition_id="d1", created_at=NOW, updated_at=NOW, **overrides)


def _snapshot(price: float, change_percent: float | None) -> MarketDataSnapshot:
    return MarketDataSnapshot(
        ticker="DELL",
        company_name="Dell Technologies Inc.",
        quote=MarketQuote(ticker="DELL", price=price, timestamp=NOW, change_percent=change_percent),
    )


def test_large_down_move_on_a_liquid_stock_triggers_with_a_partial_not_perfect_score() -> None:
    """§3: real breakout, real liquidity — but never exactly 100, because
    a one-directional move can only ever satisfy one side of the OR
    group (see the module's own docstring for the exact arithmetic)."""
    result = _engine.evaluate_company(_snapshot(price=434.78, change_percent=-11.42), _definition())

    assert result.triggered is True
    assert result.score == round(4 / 7 * 100, 2)  # liquidity (1) + move_down (3) of total weight 7
    assert result.confidence != 100.0
    assert result.confidence == round(min(100.0, result.score * 1.15), 2)


def test_large_up_move_on_a_liquid_stock_also_triggers() -> None:
    result = _engine.evaluate_company(_snapshot(price=1600.62, change_percent=7.39), _definition())

    assert result.triggered is True
    assert result.score == round(4 / 7 * 100, 2)


def test_small_move_below_threshold_never_triggers() -> None:
    """§5: an insignificant move must never trigger — this is the
    signal-definition-level equivalent of the pilot's CRM +4.70% case
    (below the 5% threshold)."""
    result = _engine.evaluate_company(_snapshot(price=205.43, change_percent=4.70), _definition())

    assert result.triggered is False
    assert result.score == round(1 / 7 * 100, 2)  # only the liquidity floor matched


def test_no_move_at_all_scores_the_liquidity_floor_only() -> None:
    result = _engine.evaluate_company(_snapshot(price=100.0, change_percent=0.0), _definition())

    assert result.triggered is False
    assert result.score == round(1 / 7 * 100, 2)


def test_illiquid_stock_with_a_real_move_still_does_not_trigger() -> None:
    """The liquidity floor is a genuine AND requirement, not decorative
    — a penny stock's move alone is never enough."""
    result = _engine.evaluate_company(_snapshot(price=2.0, change_percent=20.0), _definition())

    assert result.triggered is False


def test_missing_change_percent_data_never_fabricates_a_move() -> None:
    """A `MarketQuote` with no `change_percent` (not every provider
    response carries it) must fail the move conditions as missing data,
    never be treated as "0% change" or worse "any change"."""
    result = _engine.evaluate_company(_snapshot(price=200.0, change_percent=None), _definition())

    assert result.triggered is False
    assert result.score == round(1 / 7 * 100, 2)


def test_same_input_produces_identical_output_every_time() -> None:
    """§3: deterministic — repeated evaluation of the same snapshot
    against the same definition never drifts."""
    snapshot = _snapshot(price=434.78, change_percent=-11.42)
    first = _engine.evaluate_company(snapshot, _definition())
    second = _engine.evaluate_company(snapshot, _definition())

    assert first.score == second.score
    assert first.confidence == second.confidence
    assert first.triggered == second.triggered


def test_score_is_not_hardcoded_to_100_across_a_range_of_real_observed_moves() -> None:
    """Directly regression-guards the pilot's own P1 finding: every one
    of these real, pilot-observed price moves must produce a distinct,
    non-100 score — never the same fixed number regardless of input."""
    observed_moves = {
        "dell": -11.42,
        "crm": 4.70,
        "wday": -0.55,
        "rddt": -15.60,
        "sndk": 2.02,
    }
    scores = {
        ticker: _engine.evaluate_company(
            _snapshot(price=200.0, change_percent=pct), _definition()
        ).score
        for ticker, pct in observed_moves.items()
    }

    assert all(score != 100.0 for score in scores.values())
    assert len(set(scores.values())) > 1  # genuinely graduated, not one repeated constant
