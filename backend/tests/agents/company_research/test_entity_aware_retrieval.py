"""Tests for CompanyResearchAgent's entity-aware retrieval (Milestone 12).

Covers: entity-tagged records prioritized over pure semantic matches,
semantic retrieval preserved as a fallback (never replaced), no
duplicate records when a record matches both paths, and
CompanyOverview's new resolved-entity fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.core.context import ExecutionContext, TriggerType, WorkflowStatus
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from tests.agents.company_research.conftest import (
    build_knowledge_hub,
    build_prompt_registry,
    build_runtime,
    mock_llm_service,
    record,
)

DELL_REFERENCE = CompanyReference(
    entity_id="dell",
    canonical_name="Dell Technologies Inc.",
    ticker="DELL",
    exchange="NYSE",
    country="United States",
    sector="Technology",
    industry="Computer Hardware",
    aliases=("Dell", "Dell Technologies"),
)


def _resolver() -> EntityResolutionService:
    return EntityResolutionService((DELL_REFERENCE,))


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


def _agent(records: list, entity_resolver: EntityResolutionService | None = None) -> CompanyResearchAgent:
    return CompanyResearchAgent(
        runtime=build_runtime(),
        knowledge_hub=build_knowledge_hub(records),
        llm_service=mock_llm_service(),
        prompt_registry=build_prompt_registry(),
        entity_resolver=entity_resolver,
    )


DELL_ENTITY_TAGGED = record(
    id="dell-1",
    title="Dell stock beats Micron and AMD this year",
    text="Dell Technologies shares rose on strong earnings.",
    url="https://example.com/dell1",
    published_at="2026-08-01",
    source_provider_id="rss",
    metadata={"company": "dell", "entity_id": "dell", "entity_confidence_tier": "HIGH"},
)
DELL_SEMANTIC_ONLY = record(
    id="dell-2",
    title="Dell announces new laptop lineup",
    text="Dell unveiled several new laptop models today.",
    url="https://example.com/dell2",
    published_at="2026-08-02",
    source_provider_id="rss",
    metadata={},  # never entity-tagged (e.g. ingested before Milestone 12)
)
UNRELATED_RECORD = record(
    id="other-1",
    title="Local weather update",
    text="Sunny skies expected across the region.",
    url="https://example.com/weather",
    published_at="2026-08-01",
    source_provider_id="rss",
    metadata={},
)


# --- Entity-aware retrieval ---------------------------------------------


async def test_entity_tagged_records_are_included_when_entity_resolves() -> None:
    agent = _agent([DELL_ENTITY_TAGGED], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    record_ids = {news.record_id for news in report.latest_news}
    assert "dell-1" in record_ids


async def test_semantic_fallback_still_included_alongside_entity_matches() -> None:
    """Entity-aware retrieval supplements semantic search, it does not
    replace it — a record that was never entity-tagged (e.g. ingested
    before Milestone 12) must still surface via the pre-existing
    semantic path."""
    agent = _agent([DELL_ENTITY_TAGGED, DELL_SEMANTIC_ONLY], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    record_ids = {news.record_id for news in report.latest_news}
    assert "dell-1" in record_ids
    assert "dell-2" in record_ids


async def test_record_matched_by_both_paths_is_not_duplicated() -> None:
    agent = _agent([DELL_ENTITY_TAGGED], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    record_ids = [news.record_id for news in report.latest_news]
    assert record_ids.count("dell-1") == 1


async def test_no_entity_resolver_falls_back_to_pure_semantic_retrieval() -> None:
    """§18 regression 5: existing Research behavior remains intact when
    no entity resolver is configured at all."""
    agent = _agent([DELL_ENTITY_TAGGED, DELL_SEMANTIC_ONLY], entity_resolver=None)

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    assert report.company_overview.matched is True
    assert report.company_overview.resolved_entity_id is None
    assert report.company_overview.sector is None


async def test_unresolvable_company_with_resolver_configured_falls_back_to_semantic() -> None:
    """§18 regression 5, other direction: a resolver is configured, but
    this particular company isn't in the reference set — retrieval must
    still fall back to semantic search, not return nothing."""
    agent = _agent([UNRELATED_RECORD], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Nonexistent Company Ltd"))

    assert report.company_overview.matched is False
    assert report.company_overview.resolved_entity_id is None


# --- CompanyOverview resolved-entity fields --------------------------------


async def test_company_overview_populates_resolved_entity_fields() -> None:
    agent = _agent([DELL_ENTITY_TAGGED], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell"))

    overview = report.company_overview
    assert overview.resolved_entity_id == "dell"
    assert overview.ticker == "DELL"
    assert overview.sector == "Technology"
    assert overview.industry == "Computer Hardware"
    assert overview.country == "United States"
    assert overview.resolution_confidence == 1.0
    assert overview.resolution_method == "direct_lookup"


async def test_company_overview_resolves_by_ticker_too() -> None:
    agent = _agent([DELL_ENTITY_TAGGED], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Dell", ticker="DELL"))

    assert report.company_overview.resolved_entity_id == "dell"


async def test_unrelated_request_does_not_populate_resolved_fields() -> None:
    """§18 regression 2 (agent-level): an unrelated company name must
    never be falsely resolved to Dell or anything else."""
    agent = _agent([UNRELATED_RECORD], entity_resolver=_resolver())

    report = await agent.run(_context(), CompanyResearchRequest(company_name="Totally Unrelated Corp"))

    assert report.company_overview.resolved_entity_id is None
    assert report.company_overview.sector is None
