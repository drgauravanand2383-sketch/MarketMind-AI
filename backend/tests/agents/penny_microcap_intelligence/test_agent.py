"""Tests for PennyMicrocapIntelligenceAgent (AGT-007)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.penny_microcap_intelligence.agent import PennyMicrocapIntelligenceAgent
from app.agents.penny_microcap_intelligence.exceptions import (
    LLMGenerationError,
    PromptRenderingError,
    ReportValidationError,
    ResponseParsingError,
)
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.global_markets.models import ReportCategory
from app.prompts.registry import PromptRegistry
from app.services.llm.service import LLMAuthenticationError
from tests.agents.penny_microcap_intelligence.conftest import (
    build_prompt_registry,
    build_runtime,
    mock_llm_service,
    narrative_json,
    request,
)

_NOW = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-GLOBAL-MARKETS",
        execution_id="exec-1",
        workflow_type="global_market_intelligence",
        trigger=TriggerType.SCHEDULED,
        initiated_by="scheduler",
        started_at=_NOW,
        trace_id="trace-1",
        participating_agents=("AGT-007",),
        status=WorkflowStatus.RUNNING,
    )


def _agent(
    llm_content: str | None = None,
    llm_error: Exception | None = None,
    prompt_registry: PromptRegistry | None = None,
) -> PennyMicrocapIntelligenceAgent:
    return PennyMicrocapIntelligenceAgent(
        runtime=build_runtime(),
        llm_service=mock_llm_service(content=llm_content, error=llm_error),
        prompt_registry=prompt_registry or build_prompt_registry(),
        now_fn=lambda: _NOW,
    )


# --- Identity -----------------------------------------------------------


def test_agent_identity() -> None:
    agent = _agent()
    assert agent.agent_id == "AGT-007"
    assert agent.agent_name == "Penny/Micro-cap Intelligence"
    assert agent.layer.value == "reasoning"
    assert agent.capabilities == frozenset({"penny_microcap_intelligence"})


def test_constructor_raises_if_prompt_template_not_registered() -> None:
    with pytest.raises(PromptRenderingError):
        _agent(prompt_registry=PromptRegistry())


# --- validate_input / validate_output -----------------------------------------------------------


async def test_validate_input_accepts_a_well_formed_request() -> None:
    agent = _agent()
    assert await agent.validate_input(request()) is True


async def test_validate_input_rejects_a_main_category() -> None:
    from tests.agents.penny_microcap_intelligence.conftest import ranked_asset as penny_ranked_asset

    agent = _agent()
    req = request(
        category=ReportCategory.US_EQUITY,
        ranked_assets=(penny_ranked_asset("AAPL", 1, category=ReportCategory.US_EQUITY),),
    )
    assert await agent.validate_input(req) is False


async def test_validate_output_rejects_a_missing_risk_note() -> None:
    from app.global_markets.intelligence_report import CategoryIntelligenceReport

    agent = _agent()
    report = CategoryIntelligenceReport(
        run_id="run-1",
        category=ReportCategory.US_PENNY_STOCK,
        generated_at=_NOW,
        overall_summary="Fine.",
        risk_note=None,
        provider="anthropic",
        model="claude-sonnet-5",
    )
    assert await agent.validate_output(report) is False


# --- run(): happy path -----------------------------------------------------------


async def test_run_produces_a_report_grounded_in_the_input_assets() -> None:
    agent = _agent()

    report = await agent.run(_context(), request())

    assert report.run_id == "run-1"
    assert report.category is ReportCategory.US_PENNY_STOCK
    assert report.overall_summary == "A volatile session overall."
    assert report.asset_commentaries[0].ticker == "PENNY"
    assert report.risk_note is not None


async def test_run_tolerates_a_markdown_fenced_response() -> None:
    fenced = f"```json\n{narrative_json()}\n```"
    agent = _agent(llm_content=fenced)

    report = await agent.run(_context(), request())

    assert report.overall_summary == "A volatile session overall."


# --- run(): error handling -----------------------------------------------------------


async def test_run_raises_llm_generation_error_on_llm_failure() -> None:
    agent = _agent(llm_error=LLMAuthenticationError("bad key"))

    with pytest.raises(LLMGenerationError):
        await agent.run(_context(), request())


async def test_run_raises_response_parsing_error_on_invalid_json() -> None:
    agent = _agent(llm_content="not json")

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), request())


async def test_run_raises_report_validation_error_when_risk_note_is_null() -> None:
    """The one requirement distinguishing this agent from
    GlobalMarketsResearchAgent: risk_note must always be present here."""
    agent = _agent(llm_content=narrative_json(risk_note=None))

    with pytest.raises(ReportValidationError, match="risk_note"):
        await agent.run(_context(), request())


async def test_run_raises_report_validation_error_when_risk_note_is_whitespace_only() -> None:
    agent = _agent(llm_content=narrative_json(risk_note="   "))

    with pytest.raises(ReportValidationError, match="risk_note"):
        await agent.run(_context(), request())


async def test_run_raises_report_validation_error_on_a_whitespace_only_summary() -> None:
    agent = _agent(llm_content=narrative_json(overall_summary="   "))

    with pytest.raises(ReportValidationError):
        await agent.run(_context(), request())


async def test_run_raises_report_validation_error_on_an_ungrounded_ticker() -> None:
    agent = _agent(
        llm_content=narrative_json(
            asset_commentaries=[{"ticker": "OTHER", "rank": 1, "commentary": "Invented."}]
        )
    )

    with pytest.raises(ReportValidationError):
        await agent.run(_context(), request())


# --- health_check -----------------------------------------------------------


async def test_health_check_true_when_llm_ready_and_template_registered() -> None:
    agent = _agent()
    assert await agent.health_check() is True


async def test_health_check_false_when_llm_not_ready() -> None:
    agent = PennyMicrocapIntelligenceAgent(
        runtime=build_runtime(),
        llm_service=mock_llm_service(ready=False),
        prompt_registry=build_prompt_registry(),
    )
    assert await agent.health_check() is False


async def test_health_check_does_not_call_generate() -> None:
    agent = _agent()
    llm_service = agent._llm_service  # type: ignore[attr-defined]

    await agent.health_check()

    llm_service.generate.assert_not_called()
