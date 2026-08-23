"""Tests for the configurable canonical-entity overlay (§8/§9): file
loading/validation, alias-governance rejection, merge into
COMPANY_KEYWORDS/_ADDITIONAL_FACTS, and cache invalidation."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.services.entity_resolution import reference_data as reference_data_module
from app.services.entity_resolution.reference_overlay import (
    OverlayEntity,
    OverlayValidationError,
    apply_canonical_entity_overlay_from_path,
    apply_reference_overlay,
    load_reference_overlay,
)
from app.services.market_intelligence.engine import COMPANY_KEYWORDS


@pytest.fixture(autouse=True)
def _restore_global_reference_state() -> Iterator[None]:
    """COMPANY_KEYWORDS/_ADDITIONAL_FACTS/the memoized cache are all
    module-global mutable state — every test here must leave them exactly
    as found, or later tests (in this file and others) would observe
    leaked overlay entries."""
    keywords_snapshot = dict(COMPANY_KEYWORDS)
    facts_snapshot = dict(reference_data_module._ADDITIONAL_FACTS)
    cache_snapshot = reference_data_module._cache
    try:
        yield
    finally:
        COMPANY_KEYWORDS.clear()
        COMPANY_KEYWORDS.update(keywords_snapshot)
        reference_data_module._ADDITIONAL_FACTS.clear()
        reference_data_module._ADDITIONAL_FACTS.update(facts_snapshot)
        reference_data_module._cache = cache_snapshot


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "entity_id": "acme",
        "canonical_name": "Acme Corporation Overlay Test",
        "ticker": "ACMEX",
        "aliases": ["Acme Overlay"],
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, entries: list[dict[str, object]]) -> str:
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


EMPTY_SETS: tuple[frozenset[str], frozenset[str], frozenset[str]] = (frozenset(), frozenset(), frozenset())


# --- load_reference_overlay: file-level errors -----------------------------------------------------------


def test_missing_file_raises() -> None:
    with pytest.raises(OverlayValidationError, match="not found"):
        load_reference_overlay(
            "/no/such/path.json",
            existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_malformed_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(OverlayValidationError, match="not valid JSON"):
        load_reference_overlay(
            str(path),
            existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_non_array_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"not": "an array"}), encoding="utf-8")

    with pytest.raises(OverlayValidationError, match="JSON array"):
        load_reference_overlay(
            str(path),
            existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_entry_missing_required_field_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"entity_id": "acme"}])  # no canonical_name/ticker

    with pytest.raises(OverlayValidationError, match="malformed"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_entry_with_unknown_field_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(unknown_field="x")])

    with pytest.raises(OverlayValidationError, match="malformed"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


# --- collision validation -----------------------------------------------------------


def test_entity_id_collision_with_existing_set_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(entity_id="aapl")])

    with pytest.raises(OverlayValidationError, match="collides"):
        load_reference_overlay(
            path, existing_entity_ids=frozenset({"aapl"}), existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_ticker_collision_with_existing_set_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(ticker="AAPL")])

    with pytest.raises(OverlayValidationError, match="collides"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=frozenset({"AAPL"}), existing_canonical_names=EMPTY_SETS[2],
        )


def test_canonical_name_collision_with_existing_set_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(canonical_name="Apple Inc.")])

    with pytest.raises(OverlayValidationError, match="collides"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1],
            existing_canonical_names=frozenset({"Apple Inc."}),
        )


def test_duplicate_entity_id_within_the_file_itself_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(ticker="ACMEX"), _entry(ticker="ACMEY")])

    with pytest.raises(OverlayValidationError, match="Duplicate overlay entity_id"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


# --- alias governance (§9) -----------------------------------------------------------


def test_too_short_canonical_name_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(canonical_name="Ab")])

    with pytest.raises(OverlayValidationError, match="too short or too generic"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_generic_alias_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(aliases=["Group"])])

    with pytest.raises(OverlayValidationError, match="too short or too generic"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_too_short_alias_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry(aliases=["Ab"])])

    with pytest.raises(OverlayValidationError, match="too short or too generic"):
        load_reference_overlay(
            path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
        )


def test_alias_equal_to_ticker_is_exempt_from_length_check(tmp_path: Path) -> None:
    """A short alias equal to the ticker is matched case-sensitively as a
    ticker (see EntityResolutionService), not as a generic alias — must
    not be rejected on length grounds alone."""
    path = _write(tmp_path, [_entry(ticker="X", aliases=["X"])])

    overlay = load_reference_overlay(
        path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
    )

    assert overlay[0].ticker == "X"


def test_valid_entry_loads_successfully(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry()])

    overlay = load_reference_overlay(
        path, existing_entity_ids=EMPTY_SETS[0], existing_tickers=EMPTY_SETS[1], existing_canonical_names=EMPTY_SETS[2],
    )

    assert len(overlay) == 1
    assert isinstance(overlay[0], OverlayEntity)
    assert overlay[0].entity_id == "acme"


# --- apply_reference_overlay -----------------------------------------------------------


def test_apply_merges_into_company_keywords_and_additional_facts() -> None:
    overlay = (OverlayEntity(entity_id="acme", canonical_name="Acme Corporation Overlay Test", ticker="ACMEX", aliases=("Acme Overlay",)),)

    apply_reference_overlay(overlay)

    assert COMPANY_KEYWORDS["Acme Corporation Overlay Test"] == ("Acme Overlay",)
    assert reference_data_module._ADDITIONAL_FACTS["Acme Corporation Overlay Test"]["entity_id"] == "acme"
    assert reference_data_module._ADDITIONAL_FACTS["Acme Corporation Overlay Test"]["ticker"] == "ACMEX"


def test_apply_resets_the_memoized_reference_data_cache() -> None:
    reference_data_module.get_company_reference_data()  # populate the cache with the base set
    assert reference_data_module._cache is not None

    overlay = (OverlayEntity(entity_id="acme", canonical_name="Acme Corporation Overlay Test", ticker="ACMEX"),)
    apply_reference_overlay(overlay)

    assert reference_data_module._cache is None
    refreshed = reference_data_module.get_company_reference_data()
    assert any(ref.entity_id == "acme" for ref in refreshed)


def test_apply_empty_overlay_is_a_noop() -> None:
    before_keywords = dict(COMPANY_KEYWORDS)
    before_cache = reference_data_module._cache

    apply_reference_overlay(())

    assert before_keywords == COMPANY_KEYWORDS
    assert reference_data_module._cache is before_cache


# --- apply_canonical_entity_overlay_from_path (end-to-end) -----------------------------------------------------------


def test_end_to_end_valid_overlay_becomes_visible_via_get_company_reference_data(tmp_path: Path) -> None:
    path = _write(tmp_path, [_entry()])
    logger = logging.getLogger("test")

    apply_canonical_entity_overlay_from_path(path, logger)

    refreshed = reference_data_module.get_company_reference_data()
    assert any(ref.entity_id == "acme" and ref.ticker == "ACMEX" for ref in refreshed)


def test_end_to_end_invalid_overlay_is_skipped_not_raised(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A bad overlay must never crash startup — logged and skipped,
    exactly like every other optional-configuration degradation in
    `app.bootstrap`."""
    path = _write(tmp_path, [_entry(canonical_name="Apple Inc.")])  # collides with the real base set
    logger = logging.getLogger("test")

    with caplog.at_level(logging.WARNING):
        apply_canonical_entity_overlay_from_path(path, logger)  # must not raise

    assert "rejected" in caplog.text
    assert "Acme Corporation Overlay Test" not in COMPANY_KEYWORDS
