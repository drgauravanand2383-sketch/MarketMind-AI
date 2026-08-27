"""Tests for CompanyResearchAgent.

Covers: unit behavior, missing-company handling, multiple-company-match
resolution, empty-repository handling, evidence traceability, report
formatting, the LLM-generated narrative step, error handling, dependency
injection, and health checks. The LLM Service is always mocked — no real
Anthropic SDK or network call occurs anywhere in this file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.agents.company_research.agent import (
    CompanyResearchAgent,
    LLMGenerationError,
    PromptRenderingError,
    ReportValidationError,
    ResponseParsingError,
)
from app.agents.company_research.models import CompanyResearchRequest
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.prompts.registry import PromptRegistry
from app.services.llm.service import LLMAuthenticationError, LLMTimeoutError
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry,
    build_runtime,
    mock_llm_service,
    narrative_json,
    record,
)

APPLE_RECORD_1 = record(
    id="rec-1",
    title="Apple reports record iPhone sales",
    text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
    url="https://example.com/apple1",
    published_at="2026-08-01",
    source_provider_id="rss",
)
APPLE_TESLA_RECORD = record(
    id="rec-2",
    title="Apple and Tesla both surge on strong earnings",
    text="Shares of Apple and Tesla rallied after both reported strong quarterly earnings.",
    url="https://example.com/apple2",
    published_at="2026-08-03",
    source_provider_id="newsapi",
)
TESLA_ONLY_RECORD = record(
    id="rec-3",
    title="Tesla unveils new EV model",
    text="Tesla Inc. announced a new electric vehicle lineup this week.",
    url="https://example.com/tesla1",
    published_at="2026-08-02",
    source_provider_id="rss",
)


def _context() -> ExecutionContext:
    return ExecutionContext(
        workflow_id="WF-COMPANY-RESEARCH",
        execution_id="exec-1",
        workflow_type="company_research",
        trigger=TriggerType.USER_REQUEST,
        initiated_by="test",
        started_at=datetime.now(UTC),
        trace_id="trace-1",
        participating_agents=("AGT-004",),
        status=WorkflowStatus.RUNNING,
    )


def _agent(
    records: list,
    llm_content: str | None = None,
    llm_error: Exception | None = None,
    prompt_registry: PromptRegistry | None = None,
) -> CompanyResearchAgent:
    return CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub(records),
        llm_service=mock_llm_service(content=llm_content, error=llm_error),
        prompt_registry=prompt_registry or build_prompt_registry(),
    )


# --- Unit tests -----------------------------------------------------------


def test_agent_identity() -> None:
    agent = _agent([])
    assert agent.agent_id == "AGT-004"
    assert agent.agent_name == "Company Research"
    assert agent.layer.value == "reasoning"
    assert agent.capabilities == frozenset({"company_research"})


async def test_validate_input_rejects_empty_company_name() -> None:
    agent = _agent([])
    assert await agent.validate_input(CompanyResearchRequest(company_name="   ")) is False


async def test_validate_input_accepts_valid_request() -> None:
    agent = _agent([])
    assert await agent.validate_input(CompanyResearchRequest(company_name="Apple")) is True


async def test_validate_output_accepts_correct_type() -> None:
    agent = _agent([APPLE_RECORD_1])
    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))
    assert await agent.validate_output(report) is True


async def test_run_returns_report_for_matched_company() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.matched is True
    assert report.company_overview.entity_recognized is True
    assert report.company_overview.company_name == "Apple Inc."


async def test_report_includes_generated_at_and_original_request() -> None:
    agent = _agent([APPLE_RECORD_1])
    request = CompanyResearchRequest(company_name="Apple", ticker="AAPL")

    report = await agent.run(_context(), request)

    assert report.request == request
    assert report.generated_at is not None


# --- Missing company tests -----------------------------------------------


async def test_missing_company_returns_unmatched_report() -> None:
    agent = _agent([TESLA_ONLY_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Nonexistent Corp"))

    assert report.company_overview.matched is False
    assert report.latest_news == []
    assert report.market_intelligence.mention_count == 0


async def test_missing_company_key_risks_contains_no_data_flag() -> None:
    agent = _agent([TESLA_ONLY_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Nonexistent Corp"))

    codes = {risk.code for risk in report.key_risks}
    assert codes == {"NO_DATA"}


async def test_missing_company_all_sections_handled_without_crash() -> None:
    agent = _agent([TESLA_ONLY_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Nonexistent Corp"))

    assert report.relationship_analysis == []
    assert report.sector_analysis == []
    assert report.country_exposure == []
    assert report.supporting_evidence == []
    assert report.confidence_summary.overall_confidence == 0.0


# --- Multiple company match tests -----------------------------------------------


async def test_multiple_companies_in_results_resolves_to_requested_company() -> None:
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.company_name == "Apple Inc."
    assert report.company_overview.mention_count == 2  # rec-1 and rec-2 both mention Apple


async def test_relationship_analysis_shows_edge_to_other_mentioned_company() -> None:
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    related_labels = {ref.related_label for ref in report.relationship_analysis}
    assert "Tesla Inc." in related_labels


async def test_supporting_evidence_excludes_items_about_unrelated_company_only() -> None:
    """rec-3 (Tesla only) is not returned by the search for 'Apple', so it must not appear."""
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD, TESLA_ONLY_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    evidence_record_ids = {item.record_id for item in report.supporting_evidence}
    assert "rec-3" not in evidence_record_ids
    assert evidence_record_ids == {"rec-1", "rec-2"}


# --- Empty repository tests -----------------------------------------------


async def test_empty_repository_returns_report_without_crash() -> None:
    agent = _agent([])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report is not None
    assert report.latest_news == []


async def test_empty_repository_matched_is_false() -> None:
    agent = _agent([])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.matched is False
    assert report.key_risks[0].code == "NO_DATA"


# --- Evidence traceability tests -----------------------------------------------


async def test_supporting_evidence_items_are_traceable_to_record_ids() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert len(report.supporting_evidence) == 1
    assert report.supporting_evidence[0].record_id == "rec-1"


async def test_evidence_traceability_preserves_source_url_and_title() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    evidence = report.supporting_evidence[0]
    assert evidence.url == "https://example.com/apple1"
    assert evidence.title == "Apple reports record iPhone sales"
    assert evidence.provider == "rss"


async def test_evidence_traceability_matches_latest_news_record_ids() -> None:
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    news_ids = {item.record_id for item in report.latest_news}
    evidence_ids = {item.record_id for item in report.supporting_evidence}
    assert evidence_ids <= news_ids


async def test_include_evidence_false_produces_no_evidence_but_no_crash() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(
        _context(), CompanyResearchRequest(company_name="Apple", include_evidence=False)
    )

    assert report.supporting_evidence == []


# --- Report formatting tests -----------------------------------------------


async def test_report_has_all_nine_sections_present() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview is not None  # 1. Company Overview
    assert report.latest_news is not None  # 2. Latest News
    assert report.market_intelligence is not None  # 3. Market Intelligence
    assert report.relationship_analysis is not None  # 4. Relationship Analysis
    assert report.sector_analysis is not None  # 5. Sector Analysis
    assert report.country_exposure is not None  # 6. Country Exposure
    assert report.supporting_evidence is not None  # 7. Supporting Evidence
    assert report.confidence_summary is not None  # 8. Confidence Summary
    assert report.key_risks is not None  # 9. Key Risks


async def test_confidence_summary_reflects_supporting_record_count() -> None:
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.confidence_summary.supporting_record_count == 2
    assert report.confidence_summary.overall_confidence == 0.4  # 2 / 5 per MarketIntelligenceEngine


async def test_ticker_resolves_company_when_used_alongside_name() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(
        _context(), CompanyResearchRequest(company_name="Apple", ticker="AAPL")
    )

    assert report.company_overview.company_name == "Apple Inc."
    assert report.company_overview.ticker == "AAPL"


async def test_include_relationships_false_excludes_relationship_sections() -> None:
    agent = _agent([APPLE_RECORD_1, APPLE_TESLA_RECORD])

    report = await agent.run(
        _context(), CompanyResearchRequest(company_name="Apple", include_relationships=False)
    )

    assert report.relationship_analysis == []
    assert report.sector_analysis == []
    assert report.country_exposure == []


async def test_report_key_risks_flag_low_evidence_coverage_below_threshold() -> None:
    agent = _agent([APPLE_RECORD_1])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    codes = {risk.code for risk in report.key_risks}
    assert "LOW_EVIDENCE_COVERAGE" in codes


# --- Narrative / grounding tests -----------------------------------------------


async def test_matched_company_produces_a_narrative() -> None:
    agent = _agent([APPLE_RECORD_1], llm_content=narrative_json(summary="Apple is doing well."))

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.narrative is not None
    assert report.narrative.summary == "Apple is doing well."


async def test_unmatched_company_never_calls_the_llm() -> None:
    """No evidence retrieved -> the LLM must never be asked to reason over nothing."""
    llm_service = mock_llm_service()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([TESLA_ONLY_RECORD]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Nonexistent Corp"))

    assert report.narrative is None
    llm_service.generate.assert_not_awaited()


async def test_empty_repository_narrative_is_none() -> None:
    agent = _agent([])

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.narrative is None


# --- Prompt tests -----------------------------------------------------------


async def test_prompt_includes_company_name_evidence_relationships_and_market_intelligence() -> None:
    llm_service = mock_llm_service()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD_1, APPLE_TESLA_RECORD]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    sent_request = llm_service.generate.call_args.args[0]
    assert "Apple Inc." in sent_request.user_prompt
    assert "rec-1" in sent_request.user_prompt  # retrieved evidence
    assert "Tesla Inc." in sent_request.user_prompt  # relationships
    assert "Total records analyzed" in sent_request.user_prompt  # market intelligence


async def test_narrative_generation_requests_a_larger_max_tokens_than_the_provider_default() -> None:
    """Regression test: AnthropicProviderConfig's default max_tokens (1024)
    was observed truncating a real narrative mid-JSON
    (stop_reason="max_tokens") once retrieved evidence pushed the prompt
    to real-world size. CompanyResearchAgent must request a larger,
    explicit budget rather than relying on the provider-wide default."""
    llm_service = mock_llm_service()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD_1]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    sent_request = llm_service.generate.call_args.args[0]
    assert sent_request.max_tokens is not None
    assert sent_request.max_tokens > 1024


async def test_prompt_variables_reflect_no_evidence_and_no_relationships_gracefully() -> None:
    """Even when evidence/relationships are excluded, the prompt renders — never crashes."""
    llm_service = mock_llm_service()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD_1]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    await agent.run(
        _context(),
        CompanyResearchRequest(company_name="Apple", include_evidence=False, include_relationships=False),
    )

    sent_request = llm_service.generate.call_args.args[0]
    assert "No evidence available." in sent_request.user_prompt
    assert "No relationships identified." in sent_request.user_prompt


async def test_prompt_rendering_failure_when_template_not_registered() -> None:
    """PromptRegistry.get() is checked eagerly at construction — an
    unregistered template must never reach run()."""
    with pytest.raises(PromptRenderingError):
        CompanyResearchAgent(
            runtime=build_runtime(),
            knowledge_hub=build_knowledge_hub([]),
            llm_service=mock_llm_service(),
            prompt_registry=PromptRegistry(),  # nothing registered
        )


# --- LLM error tests -----------------------------------------------------------


async def test_llm_timeout_raises_llm_generation_error() -> None:
    agent = _agent(
        [APPLE_RECORD_1], llm_error=LLMTimeoutError("timed out", provider="anthropic")
    )

    with pytest.raises(LLMGenerationError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_llm_authentication_failure_raises_llm_generation_error() -> None:
    agent = _agent(
        [APPLE_RECORD_1],
        llm_error=LLMAuthenticationError("bad api key", provider="anthropic"),
    )

    with pytest.raises(LLMGenerationError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_llm_generation_error_never_leaks_the_underlying_llm_service_exception() -> None:
    agent = _agent(
        [APPLE_RECORD_1], llm_error=LLMTimeoutError("timed out", provider="anthropic")
    )

    with pytest.raises(LLMGenerationError) as excinfo:
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert not isinstance(excinfo.value, LLMTimeoutError)


async def test_malformed_json_raises_response_parsing_error() -> None:
    agent = _agent([APPLE_RECORD_1], llm_content="not valid json{{{")

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_empty_llm_response_raises_response_parsing_error() -> None:
    agent = _agent([APPLE_RECORD_1], llm_content="")

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_missing_required_section_raises_response_parsing_error() -> None:
    """`summary` is required on CompanyResearchNarrative; JSON missing it must be rejected."""
    agent = _agent([APPLE_RECORD_1], llm_content=json.dumps({"key_findings": ["x"]}))

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_json_array_instead_of_object_raises_response_parsing_error() -> None:
    agent = _agent([APPLE_RECORD_1], llm_content="[1, 2, 3]")

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_json_wrapped_in_markdown_code_fence_with_json_tag_is_parsed() -> None:
    """Regression test: Claude Sonnet 5 has been observed wrapping its JSON
    response in a ```json fence against the real API, despite the system
    prompt explicitly forbidding markdown fences."""
    fenced = "```json\n" + narrative_json(summary="Fenced summary.") + "\n```"
    agent = _agent([APPLE_RECORD_1], llm_content=fenced)

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.narrative is not None
    assert report.narrative.summary == "Fenced summary."


async def test_json_wrapped_in_markdown_code_fence_without_language_tag_is_parsed() -> None:
    fenced = "```\n" + narrative_json(summary="Fenced summary, no tag.") + "\n```"
    agent = _agent([APPLE_RECORD_1], llm_content=fenced)

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.narrative is not None
    assert report.narrative.summary == "Fenced summary, no tag."


async def test_invalid_json_inside_a_code_fence_still_raises_response_parsing_error() -> None:
    """Fence-stripping must not mask a genuinely malformed payload."""
    agent = _agent([APPLE_RECORD_1], llm_content="```json\nnot valid json{{{\n```")

    with pytest.raises(ResponseParsingError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


async def test_empty_summary_raises_report_validation_error() -> None:
    agent = _agent(
        [APPLE_RECORD_1],
        llm_content=json.dumps({"summary": "   ", "key_findings": [], "risk_commentary": None}),
    )

    with pytest.raises(ReportValidationError):
        await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))


# --- Dependency injection tests -----------------------------------------------------------


async def test_injected_knowledge_hub_is_used_for_retrieval() -> None:
    hub = build_knowledge_hub([APPLE_RECORD_1])
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=hub,
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
    )

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    assert report.company_overview.matched is True


async def test_injected_llm_service_is_used_for_narrative_generation() -> None:
    llm_service = mock_llm_service(content=narrative_json(summary="Custom summary."))
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD_1]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Apple"))

    llm_service.generate.assert_awaited_once()
    assert report.narrative.summary == "Custom summary."


async def test_injected_prompt_registry_is_used_for_rendering() -> None:
    registry = build_prompt_registry()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([APPLE_RECORD_1]),
        llm_service=mock_llm_service(),
        prompt_registry=registry,
    )

    # Constructing successfully at all proves the injected registry (not
    # some global/default) was consulted, since a fresh, unregistered
    # PromptRegistry would have raised at construction (see the prompt
    # rendering failure test above).
    assert agent is not None


def test_two_agents_constructed_independently_do_not_share_state() -> None:
    agent_a = _agent([APPLE_RECORD_1])
    agent_b = _agent([TESLA_ONLY_RECORD])

    assert agent_a is not agent_b
    assert agent_a._knowledge_hub is not agent_b._knowledge_hub
    assert agent_a._llm_service is not agent_b._llm_service


# --- Health check tests -----------------------------------------------------------


async def test_health_check_true_when_all_dependencies_ready() -> None:
    agent = _agent([])
    assert await agent.health_check() is True


async def test_health_check_false_when_llm_service_not_ready() -> None:
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([]),
        llm_service=mock_llm_service(ready=False),
        prompt_registry=build_prompt_registry(),
    )
    assert await agent.health_check() is False


async def test_health_check_does_not_call_generate() -> None:
    llm_service = mock_llm_service()
    agent = CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub([]),
        llm_service=llm_service,
        prompt_registry=build_prompt_registry(),
    )

    await agent.health_check()

    llm_service.generate.assert_not_awaited()
