"""Tests for ExplainabilityService's request/result management: create,
get, list, duplicate-name prevention, and not-found errors."""

from __future__ import annotations

import pytest

from app.explainability.engine import ExplainabilityService
from app.explainability.exceptions import (
    DuplicateExplainabilityRequestNameError,
    ExplainabilityRequestNotFoundError,
    ExplainabilityResultNotFoundError,
)

# --- create_request -----------------------------------------------------------


async def test_create_request_returns_a_request_with_a_generated_id(service: ExplainabilityService) -> None:
    request = await service.create_request("Explain1", "rec-1")
    assert request.id
    assert request.name == "Explain1"
    assert request.recommendation_result_id == "rec-1"


async def test_create_request_accepts_optional_references(service: ExplainabilityService) -> None:
    request = await service.create_request(
        "Explain2", "rec-1", strategy_evaluation_id="s1", risk_assessment_id="k1", backtest_run_id="b1"
    )
    assert request.strategy_evaluation_id == "s1"
    assert request.risk_assessment_id == "k1"
    assert request.backtest_run_id == "b1"


async def test_create_request_duplicate_name_raises(service: ExplainabilityService) -> None:
    await service.create_request("Explain1", "rec-1")

    with pytest.raises(DuplicateExplainabilityRequestNameError):
        await service.create_request("Explain1", "rec-2")


async def test_create_request_duplicate_name_allowed_when_not_enforced(
    explainability_repository, recommendation_service, strategy_service, risk_service, backtesting_service
) -> None:
    lenient_service = ExplainabilityService(
        explainability_repository, recommendation_service, strategy_service, risk_service, backtesting_service,
        enforce_unique_names=False,
    )
    await lenient_service.create_request("Dup", "rec-1")

    second = await lenient_service.create_request("Dup", "rec-2")

    assert second.name == "Dup"


# --- get_request / list_requests -----------------------------------------------------------


async def test_get_request_unknown_id_raises(service: ExplainabilityService) -> None:
    with pytest.raises(ExplainabilityRequestNotFoundError):
        await service.get_request("does-not-exist")


async def test_get_request_returns_created_request(service: ExplainabilityService) -> None:
    created = await service.create_request("Explain1", "rec-1")

    fetched = await service.get_request(created.id)

    assert fetched == created


async def test_list_requests_empty_initially(service: ExplainabilityService) -> None:
    assert await service.list_requests() == []


async def test_list_requests_returns_every_created_request(service: ExplainabilityService) -> None:
    await service.create_request("A", "rec-1")
    await service.create_request("B", "rec-2")

    names = {r.name for r in await service.list_requests()}

    assert names == {"A", "B"}


# --- get_result / list_results -----------------------------------------------------------


async def test_get_result_unknown_request_id_raises(service: ExplainabilityService) -> None:
    with pytest.raises(ExplainabilityResultNotFoundError):
        await service.get_result("does-not-exist")


async def test_list_results_empty_initially(service: ExplainabilityService) -> None:
    assert await service.list_results() == []
