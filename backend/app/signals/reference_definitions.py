"""Reference `SignalDefinition` factories (v1.2 Priority 1 — Selective
Signals & High-Quality Alerts).

Not a new engine capability — `SignalDetectionService`/`SignalCondition`/
`SignalConditionGroup` are unchanged; this module only assembles them into
one well-designed, genuinely graduated signal definition, in code, so the
exact same definition used in tests is also what the live-update step
(`docs/architecture/SIGNAL_ALERT_EXPLAINABILITY.md` §2) applies to the
persisted "M14 Live Price Breakout" row via the existing
`SignalDetectionService.update_signal_definition` — never a second,
drifted copy hand-typed in two places.

Design note — why this replaces the single `quote.price > 100.0`
condition: with exactly one condition at weight 1.0, `_weighted_score`
(`app.signals.engine`) can only ever output 0.0 or 100.0 — there is no
weight distribution *to* distribute. A "breakout" is, by definition, a
genuine relative price move, not a static absolute floor every real
large/mid-cap stock trivially clears forever. This definition instead
combines two independent, weighted conditions:

- A same-day move of at least 5% in *either* direction
  (`quote.change_percent`, evaluated as an OR of the up-move and
  down-move conditions — a signal condition cannot itself express
  "absolute value >= X", so two directional conditions under one OR
  group is the smallest change that expresses it) — the dominant
  condition (weight 3), because *this* is what "breakout" actually
  means.
- A liquidity/quality floor, `quote.price > 5.0` (weight 1) — excludes
  penny-stock noise a real large-cap-focused deployment has no interest
  alerting on; a defensible, universal floor, not tuned to any specific
  observed dataset.

`_weighted_score` (`app.signals.engine`) sums weight across all three
conditions (`move_up` + `move_down` + `liquidity_floor` = 3 + 3 + 1 = 7
total), not just the two in the OR group — so even a genuine, large,
one-directional move can satisfy only one of `move_up`/`move_down` by
construction (price cannot move up *and* down on the same observation).
A real triggered breakout therefore scores at most (3 + 1) / 7 ≈ 57.1%,
never 100%; a liquid stock with no qualifying move scores 1 / 7 ≈ 14.3%
and does not trigger (the OR group requires at least one side); an
illiquid stock scores 0% or ≈42.9% depending on whether it moved.
Deterministic and graduated for the same input every time — never
hardcoded, and structurally incapable of landing on a fixed number
regardless of what real price data it sees.
"""

from __future__ import annotations

from datetime import datetime

from app.signals.models import (
    SignalCategory,
    SignalCondition,
    SignalConditionGroup,
    SignalDefinition,
    SignalLogicType,
    SignalOperator,
    SignalPriority,
)

__all__ = ["build_price_breakout_signal_definition", "PRICE_BREAKOUT_SIGNAL_NAME"]

PRICE_BREAKOUT_SIGNAL_NAME = "Live Price Breakout"

DEFAULT_MOVE_THRESHOLD_PERCENT = 5.0
DEFAULT_LIQUIDITY_FLOOR = 5.0


def build_price_breakout_signal_definition(
    *,
    definition_id: str,
    created_at: datetime,
    updated_at: datetime,
    name: str = PRICE_BREAKOUT_SIGNAL_NAME,
    move_threshold_percent: float = DEFAULT_MOVE_THRESHOLD_PERCENT,
    liquidity_floor: float = DEFAULT_LIQUIDITY_FLOOR,
    enabled: bool = True,
) -> SignalDefinition:
    """Build a genuine, graduated price-breakout `SignalDefinition` — see
    the module docstring for the full rationale. `move_threshold_percent`
    and `liquidity_floor` are explicit, named parameters (never a magic
    number buried in a condition literal) so the threshold this signal
    actually enforces is visible at the call site, not just inside a
    `SignalCondition.value`.
    """
    move_group = SignalConditionGroup(id="move", logic=SignalLogicType.OR)
    return SignalDefinition(
        id=definition_id,
        name=name,
        description=(
            f"Triggers on a same-day price move of at least {move_threshold_percent:.1f}% in either "
            f"direction, for a ticker trading above ${liquidity_floor:.2f} (excludes penny-stock noise). "
            "Score is the weighted percentage of these two independent conditions that matched — never "
            "a fixed value."
        ),
        category=SignalCategory.MOMENTUM,
        enabled=enabled,
        priority=SignalPriority.HIGH,
        conditions=(
            SignalCondition(
                id="move_up",
                field="quote.change_percent",
                operator=SignalOperator.GREATER_EQUAL,
                value=move_threshold_percent,
                weight=3.0,
                group="move",
            ),
            SignalCondition(
                id="move_down",
                field="quote.change_percent",
                operator=SignalOperator.LESS_EQUAL,
                value=-move_threshold_percent,
                weight=3.0,
                group="move",
            ),
            SignalCondition(
                id="liquidity_floor",
                field="quote.price",
                operator=SignalOperator.GREATER_THAN,
                value=liquidity_floor,
                weight=1.0,
                group=None,
            ),
        ),
        groups=(move_group,),
        created_at=created_at,
        updated_at=updated_at,
    )
