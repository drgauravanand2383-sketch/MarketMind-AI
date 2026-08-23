"""PortfolioIntelligenceAgent — AGT-005.

Analyzes a portfolio of companies by reusing CompanyResearchAgent (AGT-004,
unmodified this sprint) once per holding, deterministically aggregating
the results via the existing `report_builder.build_portfolio_report()`
(also unmodified — see models.py's module docstring for why its
pre-Sprint-40 models still exist), and then adding a portfolio-level LLM
narrative on top: an executive summary, concentration observations,
relationship observations, and notable market events — all grounded in
retrieved evidence, never an investment recommendation.

Two distinct kinds of "relationships/market intelligence" appear here:
1. Per-company: already inside each CompanyResearchReport (computed by
   CompanyResearchAgent itself) — reused, never recomputed.
2. Portfolio-wide: this agent additionally queries KnowledgeHub across
   every holding and runs MarketIntelligenceEngine/RelationshipEngine over
   the combined record set, to surface genuinely cross-holding signals
   (e.g. one article mentioning two portfolio companies together) that no
   single company's own, narrower CompanyResearchReport would capture.
   This is the reason KnowledgeHub is injected directly into this agent,
   not only reached indirectly through CompanyResearchAgent.

Grounding: exactly like CompanyResearchAgent, the LLM is never called
without evidence. If no holding in the portfolio matched any retrieved
evidence, `executive_summary` falls back to an honest, deterministic "no
data" statement and every narrative list stays empty — never fabricated.

This agent never writes to knowledge storage — it only reads, through
KnowledgeHub and CompanyResearchAgent.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.agents.base import AgentLayer, BaseAgent
from app.agents.company_research.agent import CompanyResearchAgent
from app.agents.company_research.models import CompanyResearchRequest
from app.agents.portfolio_intelligence.models import (
    CompanySummary,
    Holding,
    PortfolioEvidenceReference,
    PortfolioIntelligenceReport,
    PortfolioIntelligenceRequest,
    PortfolioNarrative,
    PortfolioResearchReport,
    PortfolioResearchRequest,
    SectorOverlap,
    SharedRelationship,
)
from app.agents.portfolio_intelligence.prompts import PORTFOLIO_INTELLIGENCE_TEMPLATE_ID
from app.agents.portfolio_intelligence.report_builder import build_portfolio_report
from app.core.context import ExecutionContext
from app.core.runtime import AgentRuntime
from app.knowledge.hub import KnowledgeHub
from app.prompts.exceptions import PromptError, TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from app.repositories.knowledge.models import KnowledgeRecord
from app.services.llm.models import LLMRequest
from app.services.llm.service import LLMService, LLMServiceError
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_intelligence.models import MarketIntelligence
from app.services.relationship_engine.engine import RelationshipEngine
from app.services.relationship_engine.models import RelationshipGraph

__all__ = [
    "PortfolioIntelligenceAgentError",
    "PromptRenderingError",
    "LLMGenerationError",
    "ResponseParsingError",
    "ReportValidationError",
    "PortfolioIntelligenceAgent",
]

AGENT_ID = "AGT-005"
AGENT_NAME = "Portfolio Intelligence"
AGENT_VERSION = "0.2.0"

DEFAULT_TOP_K = 50


class PortfolioIntelligenceAgentError(Exception):
    """Base class for all AGT-005 errors. Never leaks a raw LLMService/prompt-framework exception."""

    def __init__(self, message: str, *, portfolio_name: str | None = None) -> None:
        self.portfolio_name = portfolio_name
        super().__init__(message)


class PromptRenderingError(PortfolioIntelligenceAgentError):
    """Raised when rendering the Portfolio Intelligence prompt fails (e.g. the template isn't registered)."""


class LLMGenerationError(PortfolioIntelligenceAgentError):
    """Raised when LLMService.generate() fails — timeout, auth, rate limit, provider unavailable, or config."""


class ResponseParsingError(PortfolioIntelligenceAgentError):
    """Raised when the LLM's response isn't valid JSON, or doesn't match the expected narrative schema."""


class ReportValidationError(PortfolioIntelligenceAgentError):
    """Raised when the parsed narrative fails this agent's own validation (e.g. an empty summary)."""


class PortfolioIntelligenceAgent(BaseAgent):
    """Aggregates per-holding research plus portfolio-wide signals into an LLM-narrated portfolio report."""

    def __init__(
        self,
        runtime: AgentRuntime,
        knowledge_hub: KnowledgeHub,
        llm_service: LLMService,
        prompt_registry: PromptRegistry,
        company_research_agent: CompanyResearchAgent,
    ) -> None:
        """Initialize the agent with every injected dependency.

        Args:
            runtime: The shared AgentRuntime. `runtime.memory` satisfies
                the BaseAgent contract.
            knowledge_hub: Read-only, portfolio-wide retrieval — queried
                once per holding and merged, to surface cross-holding
                signals no single CompanyResearchReport would capture.
            llm_service: Generates the narrative analysis.
            prompt_registry: Must already have the Portfolio Intelligence
                template registered (see
                `app.agents.portfolio_intelligence.prompts.register_portfolio_intelligence_prompts`)
                — this agent never registers it itself.
            company_research_agent: The already-configured CompanyResearchAgent
                (AGT-004, unmodified) invoked once per holding.

        Raises:
            PromptRenderingError: If `prompt_registry` doesn't have the
                Portfolio Intelligence template registered — checked
                eagerly here (fail fast).
        """
        super().__init__(runtime.memory)
        self._runtime = runtime
        self._knowledge_hub = knowledge_hub
        self._llm_service = llm_service
        self._prompt_registry = prompt_registry
        self._company_research_agent = company_research_agent

        try:
            prompt_registry.get(PORTFOLIO_INTELLIGENCE_TEMPLATE_ID)
        except TemplateNotFoundError as exc:
            raise PromptRenderingError(
                f"The {PORTFOLIO_INTELLIGENCE_TEMPLATE_ID!r} prompt template is not registered on the "
                "injected PromptRegistry; call "
                "app.agents.portfolio_intelligence.prompts.register_portfolio_intelligence_prompts(registry) "
                "before constructing PortfolioIntelligenceAgent."
            ) from exc

        self._renderer = PromptRenderer(prompt_registry)
        self._market_intelligence_engine = MarketIntelligenceEngine()
        self._relationship_engine = RelationshipEngine()

    @property
    def agent_id(self) -> str:
        return AGENT_ID

    @property
    def agent_name(self) -> str:
        return AGENT_NAME

    @property
    def version(self) -> str:
        return AGENT_VERSION

    @property
    def layer(self) -> AgentLayer:
        return AgentLayer.REASONING

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"portfolio_intelligence"})

    @property
    def input_schema(self) -> type[BaseModel]:
        return PortfolioIntelligenceRequest

    @property
    def output_schema(self) -> type[BaseModel]:
        return PortfolioIntelligenceReport

    async def validate_input(self, input_data: BaseModel) -> bool:
        """An empty `companies` list is valid input (an empty portfolio), not an error."""
        return isinstance(input_data, PortfolioIntelligenceRequest) and bool(
            input_data.portfolio_name.strip()
        )

    async def validate_output(self, output_data: BaseModel) -> bool:
        return isinstance(output_data, PortfolioIntelligenceReport) and bool(
            output_data.executive_summary.strip()
        )

    async def health_check(self) -> bool:
        """Verify the LLM service is ready, the prompt template exists, KnowledgeHub is
        available, and CompanyResearchAgent itself is healthy.

        Makes no LLM API request and no CompanyResearchAgent.run() call —
        only delegates to CompanyResearchAgent.health_check().
        """
        llm_status = await self._llm_service.health_check()
        if not llm_status.ready:
            return False

        try:
            self._prompt_registry.get(PORTFOLIO_INTELLIGENCE_TEMPLATE_ID)
        except TemplateNotFoundError:
            return False

        if self._knowledge_hub is None:
            return False

        return await self._company_research_agent.health_check()

    async def run(self, context: ExecutionContext, input_data: BaseModel) -> PortfolioIntelligenceReport:
        """Assemble a PortfolioIntelligenceReport: deterministic aggregation plus an LLM-grounded narrative.

        Args:
            context: The shared Execution Context for the current workflow run.
            input_data: A PortfolioIntelligenceRequest.

        Returns:
            A PortfolioIntelligenceReport. Duplicate companies (the same
            company listed more than once) each produce their own
            CompanyResearchReport — never silently deduplicated.

        Raises:
            PromptRenderingError: The Portfolio Intelligence prompt failed to render.
            LLMGenerationError: LLMService.generate() failed.
            ResponseParsingError: The LLM's response wasn't valid JSON, or
                didn't match the expected narrative schema.
            ReportValidationError: The parsed narrative failed validation
                (e.g. an empty executive summary).
        """
        assert isinstance(input_data, PortfolioIntelligenceRequest)

        company_reports = []
        for company in input_data.companies:
            company_request = CompanyResearchRequest(
                company_name=company.company_name,
                ticker=company.ticker,
                include_relationships=input_data.include_relationship_graph,
                include_evidence=input_data.include_evidence,
            )
            report = await self._company_research_agent.run(context, company_request)
            company_reports.append(report)

        legacy_report = build_portfolio_report(
            self._to_legacy_request(input_data), company_reports
        )
        company_summaries = self._build_company_summaries(input_data, legacy_report)

        if legacy_report.portfolio_overview.matched_holding_count == 0:
            # No evidence retrieved for any holding — never reason over no evidence.
            return self._build_report(
                input_data, legacy_report, company_summaries, narrative=None
            )

        portfolio_records = await self._fetch_portfolio_records(input_data)
        portfolio_market_intelligence = self._market_intelligence_engine.analyze(portfolio_records)
        portfolio_relationship_graph = (
            self._relationship_engine.build_graph(portfolio_market_intelligence)
            if input_data.include_relationship_graph
            else None
        )

        narrative = await self._generate_narrative(
            input_data, legacy_report, portfolio_market_intelligence, portfolio_relationship_graph
        )
        return self._build_report(input_data, legacy_report, company_summaries, narrative)

    def _build_report(
        self,
        input_data: PortfolioIntelligenceRequest,
        legacy_report: PortfolioResearchReport,
        company_summaries: list[CompanySummary],
        narrative: PortfolioNarrative | None,
    ) -> PortfolioIntelligenceReport:
        if narrative is not None:
            executive_summary = narrative.executive_summary
            concentration_observations = narrative.concentration_observations
            relationship_observations = narrative.relationship_observations
            notable_market_events = narrative.notable_market_events
        else:
            executive_summary = (
                "No holdings were provided for this portfolio."
                if not input_data.companies
                else (
                    "No retrieved evidence was available for any holding in this portfolio; "
                    "no narrative analysis could be grounded."
                )
            )
            concentration_observations = []
            relationship_observations = []
            notable_market_events = []

        return PortfolioIntelligenceReport(
            request=input_data,
            generated_at=legacy_report.generated_at,
            executive_summary=executive_summary,
            portfolio_overview=legacy_report.portfolio_overview,
            company_summaries=company_summaries,
            sector_exposure=legacy_report.sector_exposure,
            concentration_observations=concentration_observations,
            relationship_observations=relationship_observations,
            notable_market_events=notable_market_events,
            evidence_summary=legacy_report.evidence_summary,
            data_quality_notes=legacy_report.data_quality,
        )

    def _to_legacy_request(self, input_data: PortfolioIntelligenceRequest) -> PortfolioResearchRequest:
        """Adapt the Sprint 40 request into report_builder.py's unchanged input shape."""
        return PortfolioResearchRequest(
            portfolio_name=input_data.portfolio_name,
            holdings=[
                Holding(company_name=company.company_name, ticker=company.ticker)
                for company in input_data.companies
            ],
            include_relationship_graph=input_data.include_relationship_graph,
            include_evidence=input_data.include_evidence,
        )

    def _build_company_summaries(
        self, input_data: PortfolioIntelligenceRequest, legacy_report: PortfolioResearchReport
    ) -> list[CompanySummary]:
        weight_by_name = {company.company_name: company.weight for company in input_data.companies}
        return [
            CompanySummary(
                company_name=holding_summary.company_name,
                ticker=holding_summary.ticker,
                weight=weight_by_name.get(holding_summary.company_name),
                resolved_company_name=holding_summary.resolved_company_name,
                matched=holding_summary.matched,
                entity_recognized=holding_summary.entity_recognized,
                overall_confidence=company_report.confidence_summary.overall_confidence,
                narrative_summary=(
                    company_report.narrative.summary if company_report.narrative is not None else None
                ),
            )
            for holding_summary, company_report in zip(
                legacy_report.holdings_summary, legacy_report.company_intelligence, strict=True
            )
        ]

    async def _fetch_portfolio_records(
        self, input_data: PortfolioIntelligenceRequest
    ) -> list[KnowledgeRecord]:
        """Read-only, portfolio-wide retrieval via KnowledgeHub. Never writes.

        Queries once per holding and merges by record id, so a record
        mentioning multiple portfolio companies is only counted once.
        """
        merged: dict[str, KnowledgeRecord] = {}
        for company in input_data.companies:
            records = await self._knowledge_hub.query(company.company_name, top_k=DEFAULT_TOP_K)
            for record in records:
                merged[record.id] = record
        return list(merged.values())

    async def _generate_narrative(
        self,
        input_data: PortfolioIntelligenceRequest,
        legacy_report: PortfolioResearchReport,
        portfolio_market_intelligence: MarketIntelligence,
        portfolio_relationship_graph: RelationshipGraph | None,
    ) -> PortfolioNarrative:
        """Render the Portfolio Intelligence prompt, invoke LLMService, and parse the structured response."""
        variables = {
            "portfolio_name": input_data.portfolio_name,
            "company_summaries": self._format_company_summaries(legacy_report),
            "sector_exposure_summary": self._format_sector_exposure(legacy_report.sector_exposure),
            "shared_relationship_summary": self._format_shared_relationships(
                legacy_report.shared_relationships
            ),
            "portfolio_relationship_summary": self._format_relationship_graph(
                portfolio_relationship_graph
            ),
            "evidence_summary": self._format_evidence(legacy_report.evidence_summary),
            "user_notes": input_data.notes or "None provided.",
        }

        try:
            rendered = self._renderer.render(
                template_id=PORTFOLIO_INTELLIGENCE_TEMPLATE_ID, variables=variables
            )
        except PromptError as exc:
            raise PromptRenderingError(str(exc), portfolio_name=input_data.portfolio_name) from exc

        try:
            llm_response = await self._llm_service.generate(
                LLMRequest(system_prompt=rendered.system_prompt, user_prompt=rendered.user_prompt)
            )
        except LLMServiceError as exc:
            raise LLMGenerationError(str(exc), portfolio_name=input_data.portfolio_name) from exc

        return self._parse_narrative(llm_response.content, input_data.portfolio_name)

    def _parse_narrative(self, content: str, portfolio_name: str) -> PortfolioNarrative:
        """Parse the LLM's response content into a PortfolioNarrative.

        Raises:
            ResponseParsingError: Invalid JSON, a non-object JSON value,
                or JSON that doesn't match PortfolioNarrative's schema.
            ReportValidationError: The parsed executive_summary is empty/whitespace-only.
        """
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ResponseParsingError(
                f"LLM response was not valid JSON: {exc}", portfolio_name=portfolio_name
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseParsingError(
                "LLM response JSON must be an object", portfolio_name=portfolio_name
            )

        try:
            narrative = PortfolioNarrative(**payload)
        except PydanticValidationError as exc:
            raise ResponseParsingError(
                f"LLM response did not match the expected schema: {exc}", portfolio_name=portfolio_name
            ) from exc

        if not narrative.executive_summary.strip():
            raise ReportValidationError(
                "LLM response executive_summary was empty", portfolio_name=portfolio_name
            )

        return narrative

    @staticmethod
    def _format_company_summaries(legacy_report: PortfolioResearchReport) -> str:
        if not legacy_report.holdings_summary:
            return "No holdings."
        lines = []
        for holding_summary, company_report in zip(
            legacy_report.holdings_summary, legacy_report.company_intelligence, strict=True
        ):
            status = "matched" if holding_summary.matched else "no data found"
            confidence = company_report.confidence_summary.overall_confidence
            lines.append(
                f"- {holding_summary.resolved_company_name} ({status}, confidence={confidence:.2f})"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_sector_exposure(sector_exposure: list[SectorOverlap]) -> str:
        if not sector_exposure:
            return "No sector exposure determined."
        lines = [
            f"- {item.sector}: {', '.join(item.company_names)} "
            f"(total weight={item.total_weight}, shared={item.is_shared})"
            for item in sector_exposure
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_shared_relationships(shared_relationships: list[SharedRelationship]) -> str:
        if not shared_relationships:
            return "No relationships identified between portfolio holdings."
        lines = [
            f"- {item.company_a} <-> {item.company_b} ({item.relationship_type}, weight={item.weight})"
            for item in shared_relationships
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_relationship_graph(relationship_graph: RelationshipGraph | None) -> str:
        if relationship_graph is None or not relationship_graph.edges:
            return "No additional cross-holding relationships detected."
        labels = {node.id: node.label for node in relationship_graph.nodes}
        lines = [
            f"- {labels.get(edge.source_id, edge.source_id)} -> "
            f"{labels.get(edge.target_id, edge.target_id)} ({edge.relationship_type.value})"
            for edge in relationship_graph.edges
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_evidence(evidence_summary: list[PortfolioEvidenceReference]) -> str:
        if not evidence_summary:
            return "No evidence available."
        lines = [
            f"- [{item.record_id}] {item.title or '(untitled)'} "
            f"(companies: {', '.join(item.company_names)}, source: {item.source or 'unknown'})"
            for item in evidence_summary
        ]
        return "\n".join(lines)
