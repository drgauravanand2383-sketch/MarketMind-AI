"""UniverseRegistry — maps each `ReportCategory` to its candidate ticker set.

`get()` returning an empty tuple is a normal, honest state (see
`DEFAULT_UNIVERSES`'s own docstring for the four penny/micro-cap
categories, deliberately left empty this phase) — never an error, and
never silently substituted with invented tickers.
"""

from __future__ import annotations

from app.global_markets.models import ReportCategory
from app.global_markets.universe.models import UniverseEntry

__all__ = ["UniverseRegistry"]


class UniverseRegistry:
    """Holds one already-defined ticker universe per `ReportCategory`."""

    def __init__(self, universes: dict[ReportCategory, tuple[UniverseEntry, ...]]) -> None:
        self._universes = dict(universes)

    def get(self, category: ReportCategory) -> tuple[UniverseEntry, ...]:
        """The universe for `category`, or an empty tuple if none is configured."""
        return self._universes.get(category, ())
