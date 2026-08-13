"""Tests for WatchlistService: create/rename/delete/list/get, add/remove
company, notes, validation, duplicate prevention, and size limits."""

from __future__ import annotations

import pytest

from app.watchlist.exceptions import (
    DuplicateTickerError,
    TickerNotFoundError,
    WatchlistNotFoundError,
    WatchlistSizeLimitExceededError,
    WatchlistValidationError,
)
from app.watchlist.service import WatchlistService
from tests.watchlist.conftest import make_item

# --- create_watchlist -----------------------------------------------------------


async def test_create_watchlist_returns_a_watchlist_with_a_generated_id(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    assert watchlist.id
    assert watchlist.name == "AI"
    assert watchlist.items == ()


async def test_create_watchlist_and_get_watchlist_round_trip(service: WatchlistService) -> None:
    created = await service.create_watchlist("Semiconductors", description="Chip makers")

    fetched = await service.get_watchlist(created.id)

    assert fetched.name == "Semiconductors"
    assert fetched.description == "Chip makers"


async def test_create_watchlist_rejects_blank_name(service: WatchlistService) -> None:
    with pytest.raises(WatchlistValidationError):
        await service.create_watchlist("   ")


async def test_create_watchlist_rejects_empty_name(service: WatchlistService) -> None:
    with pytest.raises(WatchlistValidationError):
        await service.create_watchlist("")


async def test_two_watchlists_get_distinct_ids(service: WatchlistService) -> None:
    first = await service.create_watchlist("AI")
    second = await service.create_watchlist("Energy")

    assert first.id != second.id


# --- rename_watchlist -----------------------------------------------------------


async def test_rename_watchlist_updates_the_name(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    renamed = await service.rename_watchlist(watchlist.id, "Artificial Intelligence")

    assert renamed.name == "Artificial Intelligence"


async def test_rename_watchlist_unknown_id_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.rename_watchlist("does-not-exist", "New Name")


async def test_rename_watchlist_rejects_blank_name(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    with pytest.raises(WatchlistValidationError):
        await service.rename_watchlist(watchlist.id, "  ")


# --- delete_watchlist -----------------------------------------------------------


async def test_delete_watchlist_removes_it(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    await service.delete_watchlist(watchlist.id)

    with pytest.raises(WatchlistNotFoundError):
        await service.get_watchlist(watchlist.id)


async def test_delete_watchlist_unknown_id_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.delete_watchlist("does-not-exist")


# --- list_watchlists / get_watchlist -----------------------------------------------------------


async def test_list_watchlists_empty_initially(service: WatchlistService) -> None:
    assert await service.list_watchlists() == []


async def test_list_watchlists_returns_every_created_watchlist(service: WatchlistService) -> None:
    await service.create_watchlist("AI")
    await service.create_watchlist("Energy")

    names = {watchlist.name for watchlist in await service.list_watchlists()}

    assert names == {"AI", "Energy"}


async def test_get_watchlist_unknown_id_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.get_watchlist("does-not-exist")


# --- add_company -----------------------------------------------------------


async def test_add_company_adds_item_to_watchlist(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    updated = await service.add_company(watchlist.id, make_item("NVDA", company_name="NVIDIA"))

    assert [item.ticker for item in updated.items] == ["NVDA"]
    assert updated.items[0].company_name == "NVIDIA"


async def test_add_company_unknown_watchlist_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.add_company("does-not-exist", make_item("NVDA"))


async def test_add_company_duplicate_ticker_raises(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    with pytest.raises(DuplicateTickerError):
        await service.add_company(watchlist.id, make_item("NVDA"))


async def test_add_company_duplicate_ticker_is_case_insensitive(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("nvda"))

    with pytest.raises(DuplicateTickerError):
        await service.add_company(watchlist.id, make_item("NVDA"))


async def test_add_company_respects_configured_max_watchlist_size(repository) -> None:  # noqa: ANN001
    service = WatchlistService(repository, max_watchlist_size=1)
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    with pytest.raises(WatchlistSizeLimitExceededError):
        await service.add_company(watchlist.id, make_item("MSFT"))


async def test_add_company_after_removal_frees_up_space_under_the_limit(repository) -> None:  # noqa: ANN001
    service = WatchlistService(repository, max_watchlist_size=1)
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))
    await service.remove_company(watchlist.id, "NVDA")

    updated = await service.add_company(watchlist.id, make_item("MSFT"))

    assert [item.ticker for item in updated.items] == ["MSFT"]


# --- remove_company -----------------------------------------------------------


async def test_remove_company_removes_item(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    updated = await service.remove_company(watchlist.id, "NVDA")

    assert updated.items == ()


async def test_remove_company_is_case_insensitive(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    updated = await service.remove_company(watchlist.id, "nvda")

    assert updated.items == ()


async def test_remove_company_unknown_watchlist_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.remove_company("does-not-exist", "NVDA")


async def test_remove_company_ticker_not_present_raises(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    with pytest.raises(TickerNotFoundError):
        await service.remove_company(watchlist.id, "NVDA")


async def test_remove_company_does_not_affect_other_items(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))
    await service.add_company(watchlist.id, make_item("MSFT"))

    updated = await service.remove_company(watchlist.id, "NVDA")

    assert [item.ticker for item in updated.items] == ["MSFT"]


# --- update_notes -----------------------------------------------------------


async def test_update_notes_sets_the_notes_field(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    await service.add_company(watchlist.id, make_item("NVDA"))

    updated = await service.update_notes(watchlist.id, "NVDA", "Watching Q3 earnings")

    assert updated.items[0].notes == "Watching Q3 earnings"


async def test_update_notes_unknown_watchlist_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistNotFoundError):
        await service.update_notes("does-not-exist", "NVDA", "note")


async def test_update_notes_ticker_not_present_raises(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")

    with pytest.raises(TickerNotFoundError):
        await service.update_notes(watchlist.id, "NVDA", "note")


# --- Edge cases -----------------------------------------------------------


async def test_deleting_a_watchlist_does_not_affect_another(service: WatchlistService) -> None:
    first = await service.create_watchlist("AI")
    second = await service.create_watchlist("Energy")

    await service.delete_watchlist(first.id)

    assert (await service.get_watchlist(second.id)).name == "Energy"


async def test_empty_watchlist_can_be_deleted(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("Empty")
    await service.delete_watchlist(watchlist.id)  # must not raise


async def test_add_company_with_full_metadata(service: WatchlistService) -> None:
    watchlist = await service.create_watchlist("AI")
    item = make_item(
        "NVDA",
        company_name="NVIDIA",
        country="US",
        sector="Semiconductors",
        theme="AI",
        source_agent="company-research",
        confidence=0.92,
        reason="Leading AI accelerator vendor",
    )

    updated = await service.add_company(watchlist.id, item)

    stored = updated.items[0]
    assert stored.country == "US"
    assert stored.sector == "Semiconductors"
    assert stored.theme == "AI"
    assert stored.source_agent == "company-research"
    assert stored.confidence == 0.92
    assert stored.reason == "Leading AI accelerator vendor"
