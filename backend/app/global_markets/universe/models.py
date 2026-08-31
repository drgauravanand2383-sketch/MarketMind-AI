"""Universe models — the candidate ticker set each `ReportCategory` ranks over."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["UniverseEntry"]


class UniverseEntry(BaseModel):
    """One candidate asset in a category's universe — a fixed identity
    only (ticker + display name); every other fact about it (price,
    market cap, history, ...) is fetched fresh each run, never cached
    here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1)
    name: str = Field(min_length=1)
