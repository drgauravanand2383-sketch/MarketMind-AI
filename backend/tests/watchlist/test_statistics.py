"""Tests for WatchlistService's confidence statistics and snapshot generation."""

from __future__ import annotations

import pytest

from app.watchlist.exceptions import WatchlistNotFoundError
from app.watchlist.service import WatchlistService
from tests.watchlist.conftest import make_item

# --- get_statistics -----------------------------------------------------------


async def test_statistics_unknown_watchlist_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.get_statistics("does-not-exist")


async def test_statistics_for_empty_watchlist(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("Empty")

    stats = await service.get_statistics(watchlist.id)

    assert stats.total_companies == 0
    assert stats.average_confidence is None
    assert stats.top_sectors == ()
    assert stats.sector_distribution == {}
    assert stats.country_distribution == {}
    assert stats.theme_distribution == {}


async def test_average_confidence_is_computed_across_items_with_confidence(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA", confidence=0.9))
    await service.add_company(watchlist.id, make_item("MSFT", confidence=0.7))

    stats = await service.get_statistics(watchlist.id)

    assert stats.average_confidence == pytest.approx(0.8)


async def test_average_confidence_ignores_items_with_no_confidence(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA", confidence=0.8))
    await service.add_company(watchlist.id, make_item("MSFT"))  # no confidence

    stats = await service.get_statistics(watchlist.id)

    assert stats.average_confidence == pytest.approx(0.8)


async def test_average_confidence_is_none_when_no_item_has_confidence(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    stats = await service.get_statistics(watchlist.id)

    assert stats.average_confidence is None


async def test_top_sectors_is_ranked_by_frequency_descending(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA", sector="Semiconductors"))
    await service.add_company(watchlist.id, make_item("AMD", sector="Semiconductors"))
    await service.add_company(watchlist.id, make_item("MSFT", sector="Software"))

    stats = await service.get_statistics(watchlist.id)

    assert stats.top_sectors == ("Semiconductors", "Software")
    assert stats.sector_distribution == {"Semiconductors": 2, "Software": 1}


async def test_country_distribution_counts_by_country(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("Global")
    await service.add_company(watchlist.id, make_item("NVDA", country="US"))
    await service.add_company(watchlist.id, make_item("TSM", country="Taiwan"))
    await service.add_company(watchlist.id, make_item("MSFT", country="US"))

    stats = await service.get_statistics(watchlist.id)

    assert stats.country_distribution == {"US": 2, "Taiwan": 1}


async def test_theme_distribution_counts_by_theme(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("Mixed")
    await service.add_company(watchlist.id, make_item("NVDA", theme="AI"))
    await service.add_company(watchlist.id, make_item("MSFT", theme="AI"))
    await service.add_company(watchlist.id, make_item("XOM", theme="Energy"))

    stats = await service.get_statistics(watchlist.id)

    assert stats.theme_distribution == {"AI": 2, "Energy": 1}


async def test_items_missing_sector_country_theme_are_excluded_from_distributions(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))  # no sector/country/theme

    stats = await service.get_statistics(watchlist.id)

    assert stats.sector_distribution == {}
    assert stats.country_distribution == {}
    assert stats.theme_distribution == {}


async def test_statistics_reflect_removed_companies(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA", sector="Semiconductors"))
    await service.add_company(watchlist.id, make_item("MSFT", sector="Software"))
    await service.remove_company(watchlist.id, "NVDA")

    stats = await service.get_statistics(watchlist.id)

    assert stats.total_companies == 1
    assert stats.sector_distribution == {"Software": 1}


# --- generate_snapshot -----------------------------------------------------------


async def test_generate_snapshot_unknown_watchlist_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.generate_snapshot("does-not-exist")


async def test_generate_snapshot_of_empty_watchlist(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("Empty")

    snapshot = await service.generate_snapshot(watchlist.id)

    assert snapshot.watchlist_id == watchlist.id
    assert snapshot.total_companies == 0
    assert snapshot.average_confidence is None
    assert snapshot.summary


async def test_generate_snapshot_reflects_current_state(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA", confidence=0.9))
    await service.add_company(watchlist.id, make_item("MSFT", confidence=0.6))

    snapshot = await service.generate_snapshot(watchlist.id)

    assert snapshot.total_companies == 2
    assert snapshot.average_confidence == pytest.approx(0.75)


async def test_generate_snapshot_summary_mentions_the_watchlist_name(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("Semiconductors")

    snapshot = await service.generate_snapshot(watchlist.id)

    assert "Semiconductors" in snapshot.summary


async def test_multiple_snapshots_are_each_independently_recorded(
    service: WatchlistService,
) -> None:
    watchlist = await service.create_watchlist("AI")

    first = await service.generate_snapshot(watchlist.id)
    await service.add_company(watchlist.id, make_item("NVDA", confidence=0.9))
    second = await service.generate_snapshot(watchlist.id)

    assert first.total_companies == 0
    assert second.total_companies == 1
