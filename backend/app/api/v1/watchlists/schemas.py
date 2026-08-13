"""HTTP-layer request schemas for the Watchlist API.

Response bodies reuse `app.watchlist.models` directly (`Watchlist`,
`WatchlistSnapshot`, `WatchlistStatistics`) — already fully-typed Pydantic
domain models, no HTTP-specific reshaping needed.

`WatchlistItem` is NOT reused directly as the `POST /watchlists/{id}/companies`
request body: it carries an `added_at: datetime` field with no default,
which is server-assigned bookkeeping, not something a client should have to
supply. `AddCompanyRequest` exposes only the client-facing fields; the
router constructs the full `WatchlistItem` (setting `added_at` itself)
before calling `WatchlistService.add_company()`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CreateWatchlistRequest", "RenameWatchlistRequest", "AddCompanyRequest", "UpdateNotesRequest"]


class CreateWatchlistRequest(BaseModel):
    """Request body for `POST /api/v1/watchlists`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Tech Growth"])
    description: str = Field(default="", examples=["High-growth technology companies."])


class RenameWatchlistRequest(BaseModel):
    """Request body for `PATCH /api/v1/watchlists/{watchlist_id}` — the
    only update `WatchlistService` exposes is a rename."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, examples=["Tech Growth (Q3)"])


class AddCompanyRequest(BaseModel):
    """Request body for `POST /api/v1/watchlists/{watchlist_id}/companies`.

    Mirrors `app.watchlist.models.WatchlistItem` minus `added_at`, which the
    router assigns from the current server time."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, examples=["AAPL"])
    company_name: str | None = Field(default=None, examples=["Apple Inc."])
    country: str | None = Field(default=None, examples=["US"])
    sector: str | None = Field(default=None, examples=["Technology"])
    theme: str | None = Field(default=None, examples=["AI"])
    source_agent: str | None = None
    confidence: float | None = None
    reason: str | None = None
    notes: str | None = None


class UpdateNotesRequest(BaseModel):
    """Request body for `PATCH /api/v1/watchlists/{watchlist_id}/companies/{ticker}/notes`.

    Frontend Milestone 3 addition: `WatchlistService.update_notes()` has
    existed since the watchlist service was first built, but was never
    exposed over REST — `AddCompanyRequest.notes` could only ever be set
    once, at add-time. Mirrors the service method's own signature
    (`notes: str`, not optional) — send `""` to clear existing notes."""

    model_config = ConfigDict(extra="forbid")

    notes: str = Field(default="", examples=["Watching for Q3 earnings."])
