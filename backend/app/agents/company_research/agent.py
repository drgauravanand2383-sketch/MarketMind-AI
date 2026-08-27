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
import re

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
from app.knowledge.models import KnowledgeSearchFilters
from app.prompts.exceptions import PromptError, TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from app.repositories.knowledge.models import KnowledgeRecord
from app.services.entity_resolution.models import CompanyReference
from app.services.entity_resolution.service import EntityResolutionService
from app.services.evidence_engine.engine import EvidenceEngine
from app.services.evidence_engine.models import EvidenceGraph
from app.services.llm.models import LLMRequest
from app.services.llm.service import LLMService, LLMServiceError
from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_intelligence.models import MarketIntelligence
from app.services.market_snapshot.models import MarketSnapshotResult, MarketSnapshotStatus
from app.services.market_snapshot.service import MarketSnapshotService
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

# Claude Sonnet 5 occasionally wraps its JSON response in a markdown code
# fence even when the system prompt explicitly forbids it (observed
# against the real API — see _parse_narrative below); this strips one if
# present so parsing isn't hostage to prompt compliance alone.
_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)

# AnthropicProviderConfig's own default (1024) was observed truncating a
# real narrative mid-JSON (stop_reason="max_tokens") once retrieved
# evidence pushed the prompt to real-world size — adaptive thinking plus
# the structured summary/key_findings/risk_commentary payload can exceed
# it. This agent knows it always asks for a full structured narrative, so
# it requests a larger budget explicitly rather than relying on the
# provider-wide default, which other, shorter LLM calls should keep.
_NARRATIVE_MAX_TOKENS = 4096


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
        entity_resolver: EntityResolutionService | None = None,
        market_snapshot_service: MarketSnapshotService | None = None,
    ) -> None:
        """Initialize the agent with every injected dependency.

        Args:
            runtime: The shared AgentRuntime. `runtime.memory` satisfies
                the BaseAgent contract (this agent does not otherwise read
                or write memory).
            knowledge_hub: Read-only retrieval. This agent only calls
                `knowledge_hub.query(...)`/`.search(...)` — never a write
                path.
            llm_service: Generates the narrative analysis. This agent
                never imports or calls an SDK directly — only
                `LLMService.generate()`.
            prompt_registry: Must already have the Company Research
                template registered (see
                `app.agents.company_research.prompts.register_company_research_prompts`)
                — this agent never registers it itself, since owning a
                registry's contents is the caller's responsibility, not
                an agent's.
            entity_resolver: Optional EntityResolutionService (Milestone
                12). When None (the default), `_fetch_company_records`
                behaves exactly as before — pure semantic retrieval — and
                `company_overview`'s new `resolved_*`/`sector`/`industry`/
                `country` fields stay `None`. When provided,
                `request.company_name`/`.ticker` is resolved to a
                canonical entity and used for entity-aware retrieval
                (`_fetch_company_records`) alongside the existing semantic
                path, which always still runs too — see that method's own
                docstring.
            market_snapshot_service: Optional MarketSnapshotService
                (Milestone 13). When None (the default), `run()` never
                attaches a market snapshot — `CompanyResearchReport.market_snapshot`
                stays `None`, exactly like before this parameter existed.
                When provided, a snapshot for `resolved_entity` (the same
                lookup `entity_resolver` already performs — no second,
                separate resolution) is fetched and attached, honestly
                reflecting whatever `MarketSnapshotService` itself
                reports (including "no data"/"provider unavailable") —
                never fabricated, and never allowed to fail the report:
                a market-data failure degrades `market_snapshot.status`,
                it never raises out of `run()`.
        """
        super().__init__(runtime.memory)
        self._runtime = runtime
        self._knowledge_hub = knowledge_hub
        self._llm_service = llm_service
        self._prompt_registry = prompt_registry
        self._entity_resolver = entity_resolver
        self._market_snapshot_service = market_snapshot_service

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

        resolved_entity = (
            self._entity_resolver.lookup_by_name_or_ticker(input_data.company_name, input_data.ticker)
            if self._entity_resolver is not None
            else None
        )
        records = await self._fetch_company_records(input_data, resolved_entity)

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
        market_snapshot = await self._fetch_market_snapshot(resolved_entity)

        report = build_report(
            input_data,
            records,
            evidence_graph,
            market_intelligence,
            relationship_graph,
            resolved_entity,
            market_snapshot,
        )

        if not records:
            # Nothing to ground an LLM analysis in — never reason over no evidence.
            return report

        narrative = await self._generate_narrative(
            report.company_overview.company_name, evidence_graph, relationship_graph, market_intelligence
        )
        return report.model_copy(update={"narrative": narrative})

    async def _fetch_market_snapshot(
        self, resolved_entity: CompanyReference | None
    ) -> MarketSnapshotResult | None:
        """Fetch a market snapshot for `resolved_entity`, if a
        MarketSnapshotService was injected (Milestone 13).

        Returns `None` (not a `MarketSnapshotResult`) only when no
        `market_snapshot_service` was configured at all, or when the
        company itself never resolved to a canonical entity — mirroring
        `company_overview.resolved_entity_id`'s own "nothing to look up"
        case. Once a service is configured and an entity resolved, this
        always returns a `MarketSnapshotResult` (never raises): a
        market-data failure is reported honestly via `.status`, never
        allowed to fail company research itself.
        """
        if self._market_snapshot_service is None or resolved_entity is None:
            return None
        try:
            return await self._market_snapshot_service.get_snapshot(resolved_entity.entity_id)
        except Exception as exc:  # noqa: BLE001 - market data must never fail Research
            return MarketSnapshotResult(
                entity_id=resolved_entity.entity_id,
                status=MarketSnapshotStatus.UNAVAILABLE,
                reason=f"Unexpected error fetching market snapshot: {exc}",
            )

    async def _fetch_company_records(
        self, request: CompanyResearchRequest, resolved_entity: CompanyReference | None
    ) -> list[KnowledgeRecord]:
        """Read-only retrieval via KnowledgeHub. Never writes.

        Milestone 12: entity-aware retrieval, with the pre-existing
        semantic search always still performed — never replaced, only
        supplemented. When `resolved_entity` is available (this request's
        company_name/ticker resolved to a canonical entity),
        records explicitly tagged with that entity during ingestion
        (Milestone 12's `KnowledgeIngestionService` enrichment, filtered
        via `KnowledgeHub.search`'s structured `company` filter) are
        fetched and placed first — the most precise evidence available.
        Semantic results are appended after, deduplicated by id, so
        nothing semantic search alone would have found is ever lost, and a
        record found by both paths is never double-counted.
        """
        semantic_records = await self._knowledge_hub.query(request.company_name, top_k=DEFAULT_TOP_K)

        if resolved_entity is None:
            return semantic_records

        entity_records = await self._knowledge_hub.search(
            KnowledgeSearchFilters(company=resolved_entity.entity_id, top_k=DEFAULT_TOP_K)
        )
        if not entity_records:
            return semantic_records

        seen_ids = {record.id for record in entity_records}
        return [*entity_records, *(record for record in semantic_records if record.id not in seen_ids)]

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
                LLMRequest(
                    system_prompt=rendered.system_prompt,
                    user_prompt=rendered.user_prompt,
                    max_tokens=_NARRATIVE_MAX_TOKENS,
                )
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
        fence_match = _CODE_FENCE_PATTERN.match(content.strip())
        unfenced_content = fence_match.group(1) if fence_match else content

        try:
            payload = json.loads(unfenced_content)
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
