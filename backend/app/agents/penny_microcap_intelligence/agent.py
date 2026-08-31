"""PennyMicrocapIntelligenceAgent — AGT-007.

Interprets the four penny/micro-cap Global Market Intelligence
categories' already-ranked, already-eligibility-filtered `RankedAsset`s —
produced by the fully deterministic
`app.global_markets.pipeline.category_pipeline.CategoryDataPipeline`, one
level up in `GlobalMarketIntelligenceWorkflow`. Structurally identical to
`GlobalMarketsResearchAgent` (AGT-006); the difference is entirely in
tone and one extra business rule: this category's report always requires
a non-empty `risk_note` (never optional here, unlike the main-category
report) since penny/micro-cap coverage inherently carries lower data
confidence and higher volatility — see `prompts.py`'s own docstring.

Same grounding discipline as AGT-006: the LLM never sees external
knowledge, only this run's own ranked assets and market session context,
and every `asset_commentaries` entry is checked against those same input
assets after parsing (`validate_commentaries_are_grounded`) — a
hallucinated ticker/rank is rejected, never silently accepted.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.agents.base import AgentLayer, BaseAgent
from app.agents.penny_microcap_intelligence.exceptions import (
    LLMGenerationError,
    PromptRenderingError,
    ReportValidationError,
    ResponseParsingError,
)
from app.agents.penny_microcap_intelligence.models import PennyMicrocapIntelligenceRequest
from app.agents.penny_microcap_intelligence.prompts import PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID
from app.core.context import ExecutionContext
from app.core.runtime import AgentRuntime
from app.global_markets.intelligence_report import (
    CategoryIntelligenceReport,
    CategoryNarrative,
    UngroundedCommentaryError,
    validate_commentaries_are_grounded,
)
from app.global_markets.models import (
    PENNY_MICROCAP_REPORT_CATEGORIES,
    REPORT_CATEGORY_DEFINITIONS,
    MarketSessionContext,
)
from app.global_markets.ranked_asset import RankedAsset
from app.prompts.exceptions import PromptError, TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from app.services.llm.models import LLMRequest, LLMResponse
from app.services.llm.service import LLMService, LLMServiceError

__all__ = ["PennyMicrocapIntelligenceAgent"]

AGENT_ID = "AGT-007"
AGENT_NAME = "Penny/Micro-cap Intelligence"
AGENT_VERSION = "0.1.0"

_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)

_NARRATIVE_MAX_TOKENS = 4096


def _default_now() -> datetime:
    return datetime.now(UTC)


class PennyMicrocapIntelligenceAgent(BaseAgent):
    """Produces a grounded, risk-conscious narrative interpretation of one
    penny/micro-cap category's already-ranked, already-filtered assets."""

    def __init__(
        self,
        runtime: AgentRuntime,
        llm_service: LLMService,
        prompt_registry: PromptRegistry,
        *,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        """Initialize the agent with every injected dependency.

        Args:
            runtime: The shared AgentRuntime. `runtime.memory` satisfies
                the BaseAgent contract; this agent does not otherwise
                read or write memory.
            llm_service: Generates the narrative. This agent never
                imports or calls an SDK directly — only
                `LLMService.generate()`.
            prompt_registry: Must already have the Penny/Micro-cap
                Intelligence template registered (see
                `register_penny_microcap_intelligence_prompts`) — this
                agent never registers it itself.
            now_fn: Injected clock (UTC) — tests pass a fixed value for
                deterministic assertions.
        """
        super().__init__(runtime.memory)
        self._runtime = runtime
        self._llm_service = llm_service
        self._prompt_registry = prompt_registry
        self._now_fn = now_fn

        try:
            prompt_registry.get(PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID)
        except TemplateNotFoundError as exc:
            raise PromptRenderingError(
                f"The {PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID!r} prompt template is not registered on the "
                "injected PromptRegistry; call app.agents.penny_microcap_intelligence.prompts"
                ".register_penny_microcap_intelligence_prompts(registry) before constructing "
                "PennyMicrocapIntelligenceAgent."
            ) from exc

        self._renderer = PromptRenderer(prompt_registry)

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
        return frozenset({"penny_microcap_intelligence"})

    @property
    def input_schema(self) -> type[BaseModel]:
        return PennyMicrocapIntelligenceRequest

    @property
    def output_schema(self) -> type[BaseModel]:
        return CategoryIntelligenceReport

    async def validate_input(self, input_data: BaseModel) -> bool:
        return (
            isinstance(input_data, PennyMicrocapIntelligenceRequest)
            and input_data.category in PENNY_MICROCAP_REPORT_CATEGORIES
            and len(input_data.ranked_assets) > 0
        )

    async def validate_output(self, output_data: BaseModel) -> bool:
        return (
            isinstance(output_data, CategoryIntelligenceReport)
            and bool(output_data.overall_summary.strip())
            and bool((output_data.risk_note or "").strip())
        )

    async def health_check(self) -> bool:
        """Verify the LLM service is ready and the prompt template exists.

        Makes no LLM API request of its own — delegates to
        `LLMService.health_check()`.
        """
        llm_status = await self._llm_service.health_check()
        if not llm_status.ready:
            return False
        try:
            self._prompt_registry.get(PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID)
        except TemplateNotFoundError:
            return False
        return True

    async def run(self, context: ExecutionContext, input_data: BaseModel) -> CategoryIntelligenceReport:
        """Produce a `CategoryIntelligenceReport` for one penny/micro-cap category's already-ranked assets.

        Raises:
            PromptRenderingError: The prompt failed to render.
            LLMGenerationError: LLMService.generate() failed.
            ResponseParsingError: The LLM's response wasn't valid JSON, or
                didn't match the expected schema.
            ReportValidationError: The parsed narrative failed validation
                (empty summary, missing risk_note, or an ungrounded
                ticker/rank reference).
        """
        assert isinstance(input_data, PennyMicrocapIntelligenceRequest)

        narrative, llm_response = await self._generate_narrative(input_data)

        return CategoryIntelligenceReport(
            run_id=input_data.run_id,
            category=input_data.category,
            generated_at=self._now_fn(),
            overall_summary=narrative.overall_summary,
            asset_commentaries=narrative.asset_commentaries,
            risk_note=narrative.risk_note,
            provider=llm_response.provider,
            model=llm_response.model,
        )

    async def _generate_narrative(
        self, input_data: PennyMicrocapIntelligenceRequest
    ) -> tuple[CategoryNarrative, LLMResponse]:
        definition = REPORT_CATEGORY_DEFINITIONS[input_data.category]
        variables = {
            "category_display_name": definition.display_name,
            "session_summary": self._format_session(input_data.market_session_context),
            "ranked_assets_summary": self._format_ranked_assets(input_data.ranked_assets),
        }

        try:
            rendered = self._renderer.render(
                template_id=PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID, variables=variables
            )
        except PromptError as exc:
            raise PromptRenderingError(str(exc), category=input_data.category) from exc

        try:
            llm_response = await self._llm_service.generate(
                LLMRequest(
                    system_prompt=rendered.system_prompt,
                    user_prompt=rendered.user_prompt,
                    max_tokens=_NARRATIVE_MAX_TOKENS,
                )
            )
        except LLMServiceError as exc:
            raise LLMGenerationError(str(exc), category=input_data.category) from exc

        narrative = self._parse_narrative(llm_response.content, input_data)
        return narrative, llm_response

    def _parse_narrative(
        self, content: str, input_data: PennyMicrocapIntelligenceRequest
    ) -> CategoryNarrative:
        """Parse the LLM's response content into a `CategoryNarrative`.

        Raises:
            ResponseParsingError: Invalid JSON, a non-object JSON value,
                or JSON that doesn't match `CategoryNarrative`'s schema.
            ReportValidationError: An empty summary, a missing/empty
                risk_note (required for this category), or a commentary
                referencing a ticker/rank not present in the input.
        """
        fence_match = _CODE_FENCE_PATTERN.match(content.strip())
        unfenced_content = fence_match.group(1) if fence_match else content

        try:
            payload = json.loads(unfenced_content)
        except json.JSONDecodeError as exc:
            raise ResponseParsingError(
                f"LLM response was not valid JSON: {exc}", category=input_data.category
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseParsingError("LLM response JSON must be an object", category=input_data.category)

        try:
            narrative = CategoryNarrative(**payload)
        except PydanticValidationError as exc:
            raise ResponseParsingError(
                f"LLM response did not match the expected schema: {exc}", category=input_data.category
            ) from exc

        if not narrative.overall_summary.strip():
            raise ReportValidationError("LLM response overall_summary was empty", category=input_data.category)

        if not (narrative.risk_note or "").strip():
            raise ReportValidationError(
                "LLM response risk_note was empty — required for penny/micro-cap categories",
                category=input_data.category,
            )

        try:
            validate_commentaries_are_grounded(narrative.asset_commentaries, input_data.ranked_assets)
        except UngroundedCommentaryError as exc:
            raise ReportValidationError(str(exc), category=input_data.category) from exc

        return narrative

    @staticmethod
    def _format_session(session_context: MarketSessionContext) -> str:
        return (
            f"timezone={session_context.market_timezone}, "
            f"session_date={session_context.market_session_date}, "
            f"is_trading_now={session_context.is_trading_now}, "
            f"data_freshness_status={session_context.data_freshness_status.value}"
        )

    @staticmethod
    def _format_ranked_assets(ranked_assets: tuple[RankedAsset, ...]) -> str:
        lines = []
        for asset in ranked_assets:
            factor_text = ", ".join(f"{fs.factor.value}={fs.value:.1f}" for fs in asset.factor_scores)
            risk_text = asset.risk_classification.value if asset.risk_classification is not None else "UNKNOWN"
            lines.append(
                f"{asset.rank}. {asset.snapshot.ticker} — final_score={asset.final_score:.1f} | "
                f"{factor_text} | risk_classification={risk_text} | "
                f"freshness={asset.snapshot.provenance.data_freshness_status.value}"
            )
        return "\n".join(lines)
