"""CompanyResearchAgent — AGT-004.

The first real AI reasoning agent in MarketMind AI: given a company name
(and optional ticker), it retrieves related records via KnowledgeHub,
deterministically assembles every structural section of a
CompanyResearchReport by reusing the already-built EvidenceEngine,
MarketIntelligenceEngine, and RelationshipEngine (exactly as the
pre-Sprint-39 deterministic version did — see report_builder.py, which
this module still calls unchanged), and then adds one new thing: an
LLM-generated, evidence-grounded narrative analysis, produced via
LLMService and a PromptRegistry/PromptRenderer-rendered prompt.

Grounding: the LLM is NEVER given free rein. Every prompt it receives is
built entirely from this run's own retrieved evidence, relationships, and
market intelligence — never from external knowledge, and the system
prompt explicitly instructs it to reason only over what's supplied. If no
evidence was retrieved at all (an unmatched company, or an empty
repository), the LLM is never called — `CompanyResearchReport.narrative`
is simply `None`, exactly like every other field in this report already
does when there's nothing to report ("do not fabricate" is not a new rule
this sprint introduces, it's the same rule report_builder.py has always
followed, now extended to the LLM step too).

Schema note: `CompanyResearchReport.narrative` (models.py) is the one,
minimal, additive schema change this sprint required. Every other field
on every other model in that schema is untouched, still deterministic,
still computed only from retrieved evidence — this agent's `run()`
contract (`CompanyResearchRequest -> CompanyResearchReport`) is otherwise
identical to before, so `PortfolioIntelligenceAgent` (which calls this
agent once per portfolio holding and reads several of its report fields)
needs no change at all.

This agent still never writes to knowledge storage — it only reads,
through KnowledgeHub.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.agents.base import AgentLayer, BaseAgent
from app.agents.company_research.models import (
    CompanyResearchNarrative,
    CompanyResearchReport,
    CompanyResearchRequest,
)
from app.agents.company_research.prompts import COMPANY_RESEARCH_TEMPLATE_ID
from app.agents.company_research.report_builder import build_report
from app.core.context import ExecutionContext
from app.core.runtime import AgentRuntime
from app.knowledge.hub import KnowledgeHub
from app.prompts.exceptions import PromptError, TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from app.repositories.knowledge.models import KnowledgeRecord
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.evidence_engine.models import EvidenceGraph
from app.services.llm.models import LLMRequest
from app.services.llm.service import LLMService, LLMServiceError
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_intelligence.models import MarketIntelligence
from app.services.relationship_engine.engine import RelationshipEngine
from app.services.relationship_engine.models import RelationshipGraph

__all__ = [
    "CompanyResearchAgentError",
    "PromptRenderingError",
    "LLMGenerationError",
    "ResponseParsingError",
    "ReportValidationError",
    "CompanyResearchAgent",
]

AGENT_ID = "AGT-004"
AGENT_NAME = "Company Research"
AGENT_VERSION = "0.2.0"

DEFAULT_TOP_K = 50


class CompanyResearchAgentError(Exception):
    """Base class for all AGT-004 errors. Never leaks a raw LLMService/prompt-framework exception."""

    def __init__(self, message: str, *, company_name: str | None = None) -> None:
        self.company_name = company_name
        super().__init__(message)


class PromptRenderingError(CompanyResearchAgentError):
    """Raised when rendering the Company Research prompt fails (e.g. the template isn't registered)."""


class LLMGenerationError(CompanyResearchAgentError):
    """Raised when LLMService.generate() fails — timeout, auth, rate limit, provider unavailable, or config."""


class ResponseParsingError(CompanyResearchAgentError):
    """Raised when the LLM's response isn't valid JSON, or doesn't match the expected narrative schema."""


class ReportValidationError(CompanyResearchAgentError):
    """Raised when the parsed narrative fails this agent's own validation (e.g. an empty summary)."""


class CompanyResearchAgent(BaseAgent):
    """Assembles a CompanyResearchReport: deterministic structure + an LLM-generated, evidence-grounded narrative."""

    def __init__(
        self,
        runtime: AgentRuntime,
        knowledge_hub: KnowledgeHub,
        llm_service: LLMService,
        prompt_registry: PromptRegistry,
    ) -> None:
        """Initialize the agent with every injected dependency.

        Args:
            runtime: The shared AgentRuntime. `runtime.memory` satisfies
                the BaseAgent contract (this agent does not otherwise read
                or write memory).
            knowledge_hub: Read-only retrieval. This agent only calls
                `knowledge_hub.query(...)` — never a write path.
            llm_service: Generates the narrative analysis. This agent
                never imports or calls an SDK directly — only
                `LLMService.generate()`.
            prompt_registry: Must already have the Company Research
                template registered (see
                `app.agents.company_research.prompts.register_company_research_prompts`)
                — this agent never registers it itself, since owning a
                registry's contents is the caller's responsibility, not
                an agent's.

        Raises:
            PromptRenderingError: If `prompt_registry` doesn't have the
                Company Research template registered — checked eagerly
                here (fail fast) rather than on the first `run()` call.
        """
        super().__init__(runtime.memory)
        self._runtime = runtime
        self._knowledge_hub = knowledge_hub
        self._llm_service = llm_service
        self._prompt_registry = prompt_registry

        try:
            prompt_registry.get(COMPANY_RESEARCH_TEMPLATE_ID)
        except TemplateNotFoundError as exc:
            raise PromptRenderingError(
                f"The {COMPANY_RESEARCH_TEMPLATE_ID!r} prompt template is not registered on the "
                "injected PromptRegistry; call "
                "app.agents.company_research.prompts.register_company_research_prompts(registry) "
                "before constructing CompanyResearchAgent."
            ) from exc

        self._renderer = PromptRenderer(prompt_registry)
        self._evidence_engine = EvidenceEngine()
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
        return frozenset({"company_research"})

    @property
    def input_schema(self) -> type[BaseModel]:
        return CompanyResearchRequest

    @property
    def output_schema(self) -> type[BaseModel]:
        return CompanyResearchReport

    async def validate_input(self, input_data: BaseModel) -> bool:
        return isinstance(input_data, CompanyResearchRequest) and bool(
            input_data.company_name.strip()
        )

    async def validate_output(self, output_data: BaseModel) -> bool:
        if not isinstance(output_data, CompanyResearchReport):
            return False
        narrative = output_data.narrative
        return narrative is None or bool(narrative.summary.strip())

    async def health_check(self) -> bool:
        """Verify the LLM service is ready, the prompt template exists, and the knowledge hub is available.

        Makes no LLM API request of its own — delegates to
        `LLMService.health_check()`, which for the current provider
        (AnthropicProvider) makes none either.
        """
        llm_status = await self._llm_service.health_check()
        if not llm_status.ready:
            return False

        try:
            self._prompt_registry.get(COMPANY_RESEARCH_TEMPLATE_ID)
        except TemplateNotFoundError:
            return False

        return self._knowledge_hub is not None

    async def run(self, context: ExecutionContext, input_data: BaseModel) -> CompanyResearchReport:
        """Assemble a CompanyResearchReport: deterministic sections, plus an LLM-grounded narrative.

        Args:
            context: The shared Execution Context for the current workflow run.
            input_data: A CompanyResearchRequest.

        Returns:
            A CompanyResearchReport covering all nine original deterministic
            sections plus `narrative` (None if no evidence was retrieved).

        Raises:
            PromptRenderingError: The Company Research prompt failed to render.
            LLMGenerationError: LLMService.generate() failed (timeout,
                authentication, rate limit, provider unavailable, or
                LLM Service misconfiguration).
            ResponseParsingError: The LLM's response wasn't valid JSON, or
                didn't match the expected narrative schema.
            ReportValidationError: The parsed narrative failed validation
                (e.g. an empty summary).
        """
        assert isinstance(input_data, CompanyResearchRequest)

        records = await self._fetch_company_records(input_data)

        evidence_graph = (
            self._evidence_engine.build_graph(records)
            if input_data.include_evidence
            else EvidenceGraph(items=[], total_records_processed=len(records))
        )
        market_intelligence = self._market_intelligence_engine.analyze(records)
        relationship_graph = (
            self._relationship_engine.build_graph(market_intelligence)
            if input_data.include_relationships
            else None
        )

        report = build_report(
            input_data, records, evidence_graph, market_intelligence, relationship_graph
        )

        if not records:
            # Nothing to ground an LLM analysis in — never reason over no evidence.
            return report

        narrative = await self._generate_narrative(
            report.company_overview.company_name, evidence_graph, relationship_graph, market_intelligence
        )
        return report.model_copy(update={"narrative": narrative})

    async def _fetch_company_records(self, request: CompanyResearchRequest) -> list[KnowledgeRecord]:
        """Read-only retrieval via KnowledgeHub. Never writes."""
        return await self._knowledge_hub.query(request.company_name, top_k=DEFAULT_TOP_K)

    async def _generate_narrative(
        self,
        company_name: str,
        evidence_graph: EvidenceGraph,
        relationship_graph: RelationshipGraph | None,
        market_intelligence: MarketIntelligence,
    ) -> CompanyResearchNarrative:
        """Render the Company Research prompt, invoke LLMService, and parse the structured response."""
        variables = {
            "company_name": company_name,
            "evidence_summary": self._format_evidence(evidence_graph),
            "relationship_summary": self._format_relationships(relationship_graph),
            "market_intelligence_summary": self._format_market_intelligence(market_intelligence),
        }

        try:
            rendered = self._renderer.render(template_id=COMPANY_RESEARCH_TEMPLATE_ID, variables=variables)
        except PromptError as exc:
            raise PromptRenderingError(str(exc), company_name=company_name) from exc

        try:
            llm_response = await self._llm_service.generate(
                LLMRequest(system_prompt=rendered.system_prompt, user_prompt=rendered.user_prompt)
            )
        except LLMServiceError as exc:
            raise LLMGenerationError(str(exc), company_name=company_name) from exc

        return self._parse_narrative(llm_response.content, company_name)

    def _parse_narrative(self, content: str, company_name: str) -> CompanyResearchNarrative:
        """Parse the LLM's response content into a CompanyResearchNarrative.

        Raises:
            ResponseParsingError: Invalid JSON, a non-object JSON value,
                or JSON that doesn't match CompanyResearchNarrative's schema.
            ReportValidationError: The parsed summary is empty/whitespace-only.
        """
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ResponseParsingError(
                f"LLM response was not valid JSON: {exc}", company_name=company_name
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseParsingError(
                "LLM response JSON must be an object", company_name=company_name
            )

        try:
            narrative = CompanyResearchNarrative(**payload)
        except PydanticValidationError as exc:
            raise ResponseParsingError(
                f"LLM response did not match the expected schema: {exc}", company_name=company_name
            ) from exc

        if not narrative.summary.strip():
            raise ReportValidationError(
                "LLM response summary was empty", company_name=company_name
            )

        return narrative

    @staticmethod
    def _format_evidence(evidence_graph: EvidenceGraph) -> str:
        if not evidence_graph.items:
            return "No evidence available."
        lines = [
            f"- [{item.record_id}] {item.title or '(untitled)'} "
            f"(source: {item.source or 'unknown'}, published: {item.published_at or 'unknown'})"
            for item in evidence_graph.items
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_relationships(relationship_graph: RelationshipGraph | None) -> str:
        if relationship_graph is None or not relationship_graph.edges:
            return "No relationships identified."
        labels = {node.id: node.label for node in relationship_graph.nodes}
        lines = [
            f"- {labels.get(edge.source_id, edge.source_id)} -> "
            f"{labels.get(edge.target_id, edge.target_id)} ({edge.relationship_type.value})"
            for edge in relationship_graph.edges
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_market_intelligence(market_intelligence: MarketIntelligence) -> str:
        lines = [f"Total records analyzed: {market_intelligence.total_records_analyzed}"]
        if market_intelligence.companies:
            lines.append(
                "Companies: "
                + ", ".join(f"{m.name} ({m.mention_count})" for m in market_intelligence.companies)
            )
        if market_intelligence.sectors:
            lines.append(
                "Sectors: "
                + ", ".join(f"{m.name} ({m.mention_count})" for m in market_intelligence.sectors)
            )
        if market_intelligence.countries:
            lines.append(
                "Countries: "
                + ", ".join(f"{m.name} ({m.mention_count})" for m in market_intelligence.countries)
            )
        if market_intelligence.themes:
            lines.append(
                "Themes: "
                + ", ".join(f"{t.keyword} ({t.occurrence_count})" for t in market_intelligence.themes)
            )
        return "\n".join(lines)
