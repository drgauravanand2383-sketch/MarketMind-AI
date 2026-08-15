"""Configurable canonical-entity overlay (Milestone 16 §8/§9).

M12's canonical company set (`app.services.market_intelligence.engine
.COMPANY_KEYWORDS` + `app.services.entity_resolution.reference_data
._ADDITIONAL_FACTS`) is a static, hand-curated dict — adding or removing a
company has always meant editing those two source files directly. §8 asks
for "a clean mechanism to add/remove canonical entities without editing
core business logic" — this module is that mechanism: an optional,
operator-supplied JSON file (`CANONICAL_ENTITIES_OVERLAY_PATH`) of
*additional real companies*, merged into the exact same `COMPANY_KEYWORDS`
dict every consumer (`MarketIntelligenceEngine`, `EvidenceEngine`,
`EntityResolutionService` via `get_company_reference_data()`) already
reads — never a second, parallel entity model (the constraint
`reference_data.py`'s own docstring already documents), and never a
fabricated company universe: this module invents no data, it only
*validates and merges* whatever real companies an operator configures.

Deliberately NOT a place to add arbitrarily many companies at once: no
default overlay ships with this codebase, the file is opt-in
(`CANONICAL_ENTITIES_OVERLAY_PATH` unset -> no overlay, zero behavior
change from Milestone 15), and every entry is validated before merging —
see `_validate_entry` for the concrete alias-governance rules (§9):
duplicate entity_id/ticker/canonical_name against the existing set is
rejected outright (never silently overwrites a real, already-known
company), and any alias/canonical_name that is too short or a member of
`_GENERIC_ALIAS_STOPWORDS` is rejected — exactly the class of "ordinary
English word" false-positive `EntityResolutionService._find_ticker_occurrences`'s
own docstring already identifies as a real risk for short tickers, applied
here at *configuration load time* instead, so a bad overlay entry never
reaches the scoring engine at all (candidate auditability: every rejection
is a specific, logged reason, not a silent drop).

Must be applied once, at process startup, before the first
`get_company_reference_data()` call (which caches its result) — see
`app.bootstrap.apply_canonical_entity_overlay_from_path`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "OverlayEntity",
    "OverlayValidationError",
    "load_reference_overlay",
    "apply_reference_overlay",
    "apply_canonical_entity_overlay_from_path",
]

_logger = logging.getLogger("marketmind.services.entity_resolution.reference_overlay")

# Minimum alias/canonical_name length: below this, whole-word matching
# (EntityResolutionService._find_occurrences) false-matches too easily
# against ordinary short English tokens ("Go", "It", "On", ...).
_MIN_ALIAS_LENGTH = 3

# A small, deliberately conservative stoplist of generic business words
# that are real substrings of countless unrelated companies' names/aliases
# — accepting one of these as a bare alias would make *every* mention of
# the word itself a false-positive match, defeating the whole point of
# whole-word alias matching. Not exhaustive by design: only words common
# enough in ordinary financial prose to matter; anything not on this list
# still goes through normal whole-word matching in
# `EntityResolutionService`, which already has its own ticker-specific
# case-sensitivity safeguard for the "short alias == ordinary word" case.
_GENERIC_ALIAS_STOPWORDS: frozenset[str] = frozenset({
    "the", "inc", "corp", "co", "group", "company", "companies", "market",
    "markets", "stock", "stocks", "shares", "share", "fund", "holdings",
    "capital", "global", "international", "national", "industries",
    "enterprises", "technologies", "tech", "systems", "solutions",
    "services", "partners", "ventures", "news", "data", "products",
})


class OverlayEntity(BaseModel):
    """One validated additional canonical entity from the overlay file.
    Same field shape as `CompanyReference` (see that model's own
    docstring for why this is deliberately a superset, not a parallel
    model) — `ticker`/`aliases` are required here (unlike
    `CompanyReference`, where they're optional) because an overlay entry
    with no ticker or no way to be matched in text would be pointless."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    aliases: tuple[str, ...] = Field(default_factory=tuple)
    legal_name: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None


class OverlayValidationError(Exception):
    """Raised when an overlay file is malformed, or an entry fails
    alias-governance/collision validation. Never raised for a merely
    *missing/unset* overlay path — that is simply "no overlay," not an error."""


def _is_generic_alias(term: str) -> bool:
    normalized = term.strip().lower()
    return len(normalized) < _MIN_ALIAS_LENGTH or normalized in _GENERIC_ALIAS_STOPWORDS


def _validate_entry(
    entry: OverlayEntity,
    *,
    existing_entity_ids: frozenset[str],
    existing_tickers: frozenset[str],
    existing_canonical_names: frozenset[str],
) -> None:
    if entry.entity_id in existing_entity_ids:
        raise OverlayValidationError(
            f"Overlay entity_id {entry.entity_id!r} collides with an existing canonical entity."
        )
    if entry.ticker.upper() in existing_tickers:
        raise OverlayValidationError(
            f"Overlay ticker {entry.ticker!r} collides with an existing canonical entity."
        )
    if entry.canonical_name in existing_canonical_names:
        raise OverlayValidationError(
            f"Overlay canonical_name {entry.canonical_name!r} collides with an existing canonical entity."
        )
    if _is_generic_alias(entry.canonical_name):
        raise OverlayValidationError(
            f"Overlay canonical_name {entry.canonical_name!r} is too short or too generic to match safely."
        )
    for alias in entry.aliases:
        if alias == entry.ticker:
            continue  # matched case-sensitively as a ticker, not as a generic alias — see EntityResolutionService
        if _is_generic_alias(alias):
            raise OverlayValidationError(
                f"Overlay alias {alias!r} for {entry.canonical_name!r} is too short or too generic to match safely "
                f"(minimum length {_MIN_ALIAS_LENGTH}, and must not be a generic business word)."
            )


def load_reference_overlay(
    path: str,
    *,
    existing_entity_ids: frozenset[str],
    existing_tickers: frozenset[str],
    existing_canonical_names: frozenset[str],
) -> tuple[OverlayEntity, ...]:
    """Read and validate the overlay JSON file at `path`.

    The file must contain a JSON array of objects, each matching
    `OverlayEntity`'s fields. Raises `OverlayValidationError` for a
    malformed file or any entry that fails validation — a bad overlay
    must fail loudly at startup, never be silently dropped or partially
    applied.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OverlayValidationError(f"Canonical entity overlay file not found: {path!r}") from exc
    except json.JSONDecodeError as exc:
        raise OverlayValidationError(f"Canonical entity overlay file {path!r} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise OverlayValidationError(f"Canonical entity overlay file {path!r} must contain a JSON array.")

    entries: list[OverlayEntity] = []
    seen_entity_ids: set[str] = set()
    seen_tickers: set[str] = set()
    for index, item in enumerate(raw):
        try:
            entry = OverlayEntity.model_validate(item)
        except ValidationError as exc:
            raise OverlayValidationError(f"Overlay entry {index} is malformed: {exc}") from exc
        _validate_entry(
            entry,
            existing_entity_ids=existing_entity_ids,
            existing_tickers=existing_tickers,
            existing_canonical_names=existing_canonical_names,
        )
        if entry.entity_id in seen_entity_ids:
            raise OverlayValidationError(f"Duplicate overlay entity_id {entry.entity_id!r} within the overlay file itself.")
        if entry.ticker.upper() in seen_tickers:
            raise OverlayValidationError(f"Duplicate overlay ticker {entry.ticker!r} within the overlay file itself.")
        seen_entity_ids.add(entry.entity_id)
        seen_tickers.add(entry.ticker.upper())
        entries.append(entry)

    _logger.info(
        "canonical_entity_overlay_loaded",
        extra={"path": path, "entity_count": len(entries)},
    )
    return tuple(entries)


def apply_reference_overlay(overlay: tuple[OverlayEntity, ...]) -> None:
    """Merge already-validated overlay entries into `COMPANY_KEYWORDS`
    (module-global) and `entity_resolution.reference_data._ADDITIONAL_FACTS`
    — the one canonical entity set every consumer reads, not a second one.
    Also invalidates `reference_data`'s own memoized
    `get_company_reference_data()` result, so the next call rebuilds it
    including these entries rather than returning a stale, pre-overlay
    cache (that function caches on first call; without this reset, an
    overlay applied after any earlier call — including this function's
    own collision-checking read — would silently never take effect).

    Must be called before the first *externally visible* use of
    `get_company_reference_data()`/`EntityResolutionService` in the
    process — see `apply_canonical_entity_overlay_from_path`, the
    single entrypoint `app.bootstrap` calls.
    """
    if not overlay:
        return

    # Deferred import: matches `reference_data.py`'s own deferred-import
    # rationale (avoids the same import cycle through
    # market_intelligence.engine -> ... -> entity_resolution.service).
    from app.services.entity_resolution import reference_data as reference_data_module
    from app.services.market_intelligence.engine import COMPANY_KEYWORDS

    for entry in overlay:
        COMPANY_KEYWORDS[entry.canonical_name] = entry.aliases
        reference_data_module._ADDITIONAL_FACTS[entry.canonical_name] = {
            key: value
            for key, value in {
                "entity_id": entry.entity_id,
                "legal_name": entry.legal_name or entry.canonical_name,
                "ticker": entry.ticker,
                "exchange": entry.exchange,
                "country": entry.country,
                "sector": entry.sector,
                "industry": entry.industry,
            }.items()
            if value is not None
        }
        _logger.info(
            "canonical_entity_overlay_applied",
            extra={"entity_id": entry.entity_id, "canonical_name": entry.canonical_name},
        )
    reference_data_module._cache = None


def apply_canonical_entity_overlay_from_path(path: str, logger: logging.Logger) -> None:
    """Load, validate, and apply the overlay file at `path` — the single
    entrypoint `app.bootstrap` calls. A malformed or invalid overlay is
    logged and skipped (the base canonical entity set — never empty —
    remains fully usable); this must never crash startup, matching every
    other optional-configuration degradation in `app.bootstrap`.

    Reads `COMPANY_KEYWORDS`/`_ADDITIONAL_FACTS` directly for
    collision-checking (not `get_company_reference_data()`) — calling
    that cached accessor here would freeze its result *before* the
    overlay is merged, exactly the staleness `apply_reference_overlay`'s
    own cache reset exists to prevent.
    """
    # Deferred import: same import-cycle rationale as `apply_reference_overlay`.
    from app.services.entity_resolution.reference_data import _ADDITIONAL_FACTS
    from app.services.market_intelligence.engine import COMPANY_KEYWORDS

    existing_entity_ids = frozenset(facts["entity_id"] for facts in _ADDITIONAL_FACTS.values())
    existing_tickers = frozenset(
        facts["ticker"].upper() for facts in _ADDITIONAL_FACTS.values() if facts.get("ticker")
    )
    existing_canonical_names = frozenset(COMPANY_KEYWORDS.keys())

    try:
        overlay = load_reference_overlay(
            path,
            existing_entity_ids=existing_entity_ids,
            existing_tickers=existing_tickers,
            existing_canonical_names=existing_canonical_names,
        )
    except OverlayValidationError as exc:
        logger.warning("Canonical entity overlay rejected; continuing without it: %s", exc)
        return
    apply_reference_overlay(overlay)
