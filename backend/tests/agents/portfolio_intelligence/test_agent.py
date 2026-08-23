"""Tests for PortfolioIntelligenceAgent.

Covers: unit behavior, empty portfolios, single/multi-company aggregation,
duplicate companies, missing companies, the LLM-generated narrative step,
prompt rendering, error handling, dependency injection, and health checks.
Only LLMService is mocked — the Prompt Framework, KnowledgeHub, and
CompanyResearchAgent are all real; no network or database call occurs
anywhere in this file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.agents.portfolio_intelligence.agent import (
    LLMGenerationError,
    PromptRenderingError,
    ReportValidationError,
    ResponseParsingError,
)
from app.agents.portfolio_intelligence.models import PortfolioCompanyRequest, PortfolioIntelligenceRequest
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.prompts.registry import PromptRegistry
from app.services.llm.service import LLMTimeoutError
from tests.agents.portfolio_intelligence.conftest import (
    APPLE_RECORD,
    APPLE_TESLA_RECORD,
    TESLA_RECORD,
    build_portfolio_agent,
    portfolio_narrative_json,
)


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-PORTFOLIO-INTELLIGENCE",
        execution_id="exec-1",
        workflow_type="portfolio_intelligence",
        trigger=TriggerType.USER_REQUEST,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id="trace-1",
        participating_agents=("AGT-005",),
        status=WorkflowStatus.RUNNING,
    )


def _company(name: str, **overrides: object) -> PortfolioCompanyRequest:
    return PortfolioCompanyRequest(company_name=name, **overrides)


# --- Unit tests -----------------------------------------------------------


def test_agent_identity() -> None:
    agent = build_portfolio_agent([])
    assert agent.agent_id == "AGT-005"
    assert agent.agent_name == "Portfolio Intelligence"
    assert agent.layer.value == "reasoning"
    assert agent.capabilities == frozenset({"portfolio_intelligence"})


async def test_validate_input_accepts_empty_companies() -> None:
    agent = build_portfolio_agent([])
    request = PortfolioIntelligenceRequest(portfolio_name="My Portfolio", companies=[])
    assert await agent.validate_input(request) is True


async def test_validate_input_rejects_empty_portfolio_name() -> None:
    agent = build_portfolio_agent([])
    request = PortfolioIntelligenceRequest(portfolio_name="   ", companies=[])
    assert await agent.validate_input(request) is False


async def test_validate_output_accepts_correct_type() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])
    report = await agent.run(_context(), request)
    assert await agent.validate_output(report) is True


# --- Empty portfolio tests -----------------------------------------------


async def test_empty_portfolio_produces_valid_report_without_crash() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="Empty Portfolio", companies=[])

    report = await agent.run(_context(), request)

    assert report is not None
    assert report.portfolio_overview.holding_count == 0


async def test_empty_portfolio_overview_reflects_zero_companies() -> None:
    agent = build_portfolio_agent([])
    request = PortfolioIntelligenceRequest(portfolio_name="Empty Portfolio", companies=[])

    report = await agent.run(_context(), request)

    assert report.portfolio_overview.matched_holding_count == 0
    assert report.company_summaries == []


async def test_empty_portfolio_all_aggregation_sections_are_empty() -> None:
    agent = build_portfolio_agent([])
    request = PortfolioIntelligenceRequest(portfolio_name="Empty Portfolio", companies=[])

    report = await agent.run(_context(), request)

    assert report.sector_exposure == []
    assert report.evidence_summary == []
    assert report.data_quality_notes == []
    assert report.concentration_observations == []
    assert report.relationship_observations == []
    assert report.notable_market_events == []


async def test_empty_portfolio_never_calls_the_llm() -> None:
    agent = build_portfolio_agent([])
    request = PortfolioIntelligenceRequest(portfolio_name="Empty Portfolio", companies=[])

    await agent.run(_context(), request)

    agent._llm_service.generate.assert_not_awaited()


async def test_unmatched_portfolio_never_calls_the_llm() -> None:
    """No company in the portfolio matched any evidence -> never reason over nothing."""
    agent = build_portfolio_agent([TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Nonexistent Corp")]
    )

    report = await agent.run(_context(), request)

    agent._llm_service.generate.assert_not_awaited()
    assert report.executive_summary  # a deterministic fallback, never empty


# --- Single company tests -----------------------------------------------


async def test_single_company_produces_one_company_summary() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    assert len(report.company_summaries) == 1
    assert report.company_summaries[0].resolved_company_name == "Apple Inc."


async def test_single_company_sector_is_not_marked_shared() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    technology = next((s for s in report.sector_exposure if s.sector == "Technology"), None)
    assert technology is not None
    assert technology.is_shared is False
    assert technology.company_names == ["Apple Inc."]


async def test_company_summary_carries_the_requested_weight() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple", weight=0.6)]
    )

    report = await agent.run(_context(), request)

    assert report.company_summaries[0].weight == 0.6


async def test_company_summary_includes_the_narrative_from_company_research_agent() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    assert report.company_summaries[0].narrative_summary is not None


# --- Multi-company tests -----------------------------------------------


async def test_multi_company_detects_overlapping_sector() -> None:
    agent = build_portfolio_agent([APPLE_RECORD, TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Tesla")]
    )

    report = await agent.run(_context(), request)

    technology = next((s for s in report.sector_exposure if s.sector == "Technology"), None)
    assert technology is not None
    assert technology.is_shared is True
    assert set(technology.company_names) == {"Apple Inc.", "Tesla Inc."}


async def test_multi_company_detects_shared_evidence() -> None:
    agent = build_portfolio_agent([APPLE_RECORD, TESLA_RECORD, APPLE_TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Tesla")]
    )

    report = await agent.run(_context(), request)

    shared_record = next((e for e in report.evidence_summary if e.record_id == "rec-both"), None)
    assert shared_record is not None
    assert shared_record.is_shared is True
    assert set(shared_record.company_names) == {"Apple Inc.", "Tesla Inc."}


# --- Duplicate company tests -----------------------------------------------


async def test_duplicate_company_produces_two_company_summaries() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Apple")]
    )

    report = await agent.run(_context(), request)

    assert report.portfolio_overview.holding_count == 2
    assert len(report.company_summaries) == 2


async def test_duplicate_company_does_not_falsely_mark_sector_as_shared() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Apple")]
    )

    report = await agent.run(_context(), request)

    technology = next((s for s in report.sector_exposure if s.sector == "Technology"), None)
    assert technology is not None
    assert technology.is_shared is False  # same company twice, not two distinct companies


# --- Missing company tests -----------------------------------------------


async def test_missing_company_included_but_unmatched() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Nonexistent Corp")]
    )

    report = await agent.run(_context(), request)

    assert len(report.company_summaries) == 2
    missing = next(c for c in report.company_summaries if c.company_name == "Nonexistent Corp")
    assert missing.matched is False
    assert report.portfolio_overview.matched_holding_count == 1


async def test_missing_company_flagged_in_data_quality_notes() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Nonexistent Corp")]
    )

    report = await agent.run(_context(), request)

    no_data_flag = next((f for f in report.data_quality_notes if f.code == "NO_DATA"), None)
    assert no_data_flag is not None
    assert no_data_flag.affected_company_count == 1


# --- include_evidence / include_relationship_graph -----------------------------------------------


async def test_include_evidence_false_excludes_evidence_summary() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple")], include_evidence=False
    )

    report = await agent.run(_context(), request)

    assert report.evidence_summary == []


async def test_include_relationship_graph_false_still_produces_a_report() -> None:
    agent = build_portfolio_agent([APPLE_RECORD, TESLA_RECORD, APPLE_TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P",
        companies=[_company("Apple"), _company("Tesla")],
        include_relationship_graph=False,
    )

    report = await agent.run(_context(), request)

    assert report is not None


# --- Report formatting -----------------------------------------------


async def test_report_has_all_nine_sections_present() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    assert report.executive_summary  # 1
    assert report.portfolio_overview is not None  # 2
    assert report.company_summaries is not None  # 3
    assert report.sector_exposure is not None  # 4
    assert report.concentration_observations is not None  # 5
    assert report.relationship_observations is not None  # 6
    assert report.notable_market_events is not None  # 7
    assert report.evidence_summary is not None  # 8
    assert report.data_quality_notes is not None  # 9


# --- Prompt tests -----------------------------------------------------------


async def test_prompt_includes_portfolio_name_company_summaries_and_evidence() -> None:
    agent = build_portfolio_agent([APPLE_RECORD, TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="My Portfolio", companies=[_company("Apple"), _company("Tesla")]
    )

    await agent.run(_context(), request)

    sent_request = agent._llm_service.generate.call_args.args[0]
    assert "My Portfolio" in sent_request.user_prompt
    assert "Apple Inc." in sent_request.user_prompt
    assert "Tesla Inc." in sent_request.user_prompt
    assert "rec-apple" in sent_request.user_prompt


async def test_prompt_includes_user_notes() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple")], notes="Please focus on chip supply risk."
    )

    await agent.run(_context(), request)

    sent_request = agent._llm_service.generate.call_args.args[0]
    assert "Please focus on chip supply risk." in sent_request.user_prompt


async def test_prompt_defaults_user_notes_when_none_provided() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    await agent.run(_context(), request)

    sent_request = agent._llm_service.generate.call_args.args[0]
    assert "None provided." in sent_request.user_prompt


async def test_prompt_rendering_failure_when_template_not_registered() -> None:
    with pytest.raises(PromptRenderingError):
        build_portfolio_agent([], prompt_registry=PromptRegistry())


# --- LLM error / validation tests -----------------------------------------------------------


async def test_llm_timeout_raises_llm_generation_error() -> None:
    agent = build_portfolio_agent(
        [APPLE_RECORD], llm_error=LLMTimeoutError("timed out", provider="anthropic")
    )
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(LLMGenerationError):
        await agent.run(_context(), request)


async def test_malformed_json_raises_response_parsing_error() -> None:
    agent = build_portfolio_agent([APPLE_RECORD], llm_content="not valid json{{{")
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), request)


async def test_empty_llm_response_raises_response_parsing_error() -> None:
    agent = build_portfolio_agent([APPLE_RECORD], llm_content="")
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), request)


async def test_missing_required_section_raises_response_parsing_error() -> None:
    """`executive_summary` is required on PortfolioNarrative; JSON missing it must be rejected."""
    agent = build_portfolio_agent(
        [APPLE_RECORD], llm_content=json.dumps({"concentration_observations": ["x"]})
    )
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), request)


async def test_json_array_instead_of_object_raises_response_parsing_error() -> None:
    agent = build_portfolio_agent([APPLE_RECORD], llm_content="[1, 2, 3]")
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), request)


async def test_empty_executive_summary_raises_report_validation_error() -> None:
    agent = build_portfolio_agent(
        [APPLE_RECORD],
        llm_content=json.dumps(
            {
                "executive_summary": "   ",
                "concentration_observations": [],
                "relationship_observations": [],
                "notable_market_events": [],
            }
        ),
    )
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    with pytest.raises(ReportValidationError):
        await agent.run(_context(), request)


# --- Dependency injection tests -----------------------------------------------------------


async def test_injected_llm_service_is_used_for_narrative_generation() -> None:
    agent = build_portfolio_agent(
        [APPLE_RECORD], llm_content=portfolio_narrative_json(executive_summary="Custom summary.")
    )
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    agent._llm_service.generate.assert_awaited_once()
    assert report.executive_summary == "Custom summary."


async def test_injected_knowledge_hub_is_used_for_portfolio_wide_retrieval() -> None:
    """A portfolio-wide relationship (from `rec-both`, which mentions both
    holdings) only appears in the prompt if PortfolioIntelligenceAgent
    actually queried KnowledgeHub across every holding and re-ran
    MarketIntelligenceEngine/RelationshipEngine over the combined records —
    proving the injected KnowledgeHub was genuinely used, not bypassed."""
    agent = build_portfolio_agent([APPLE_RECORD, TESLA_RECORD, APPLE_TESLA_RECORD])
    request = PortfolioIntelligenceRequest(
        portfolio_name="P", companies=[_company("Apple"), _company("Tesla")]
    )

    await agent.run(_context(), request)

    sent_request = agent._llm_service.generate.call_args.args[0]
    assert "company_to_company" in sent_request.user_prompt


async def test_injected_company_research_agent_is_used() -> None:
    agent = build_portfolio_agent([APPLE_RECORD])
    request = PortfolioIntelligenceRequest(portfolio_name="P", companies=[_company("Apple")])

    report = await agent.run(_context(), request)

    # CompanyResearchAgent's own narrative made it into the company summary,
    # proving the injected agent (not some bypass) actually ran.
    assert report.company_summaries[0].narrative_summary is not None


def test_two_agents_constructed_independently_do_not_share_state() -> None:
    agent_a = build_portfolio_agent([APPLE_RECORD])
    agent_b = build_portfolio_agent([TESLA_RECORD])

    assert agent_a is not agent_b
    assert agent_a._knowledge_hub is not agent_b._knowledge_hub
    assert agent_a._llm_service is not agent_b._llm_service
    assert agent_a._company_research_agent is not agent_b._company_research_agent


# --- Health check tests -----------------------------------------------------------


async def test_health_check_true_when_all_dependencies_ready() -> None:
    agent = build_portfolio_agent([])
    assert await agent.health_check() is True


async def test_health_check_false_when_llm_service_not_ready() -> None:
    agent = build_portfolio_agent([], llm_ready=False)
    assert await agent.health_check() is False


async def test_health_check_does_not_call_generate() -> None:
    agent = build_portfolio_agent([])

    await agent.health_check()

    agent._llm_service.generate.assert_not_awaited()
