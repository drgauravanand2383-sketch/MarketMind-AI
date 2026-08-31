"""The Global Markets Research prompt template — registered via PromptRegistry.

Contains no reasoning of its own — only the declarative `PromptTemplate`
`GlobalMarketsResearchAgent` renders and sends to `LLMService`. Grounding
is enforced structurally: the template instructs the model to reason only
over the supplied ranked-asset data, and every "ticker"/"rank" pair it
returns is checked against that same data afterward (see
`app.global_markets.intelligence_report.validate_commentaries_are_grounded`).

Per `app.prompts.registry.PromptRegistry`'s own contract, this template is
never auto-discovered: `register_global_markets_research_prompts()` must
be called explicitly, with an already-constructed `PromptRegistry`, before
that registry is injected into `GlobalMarketsResearchAgent`.
"""

from __future__ import annotations

from app.prompts.registry import PromptRegistry
from app.prompts.template import PromptTemplate

__all__ = [
    "GLOBAL_MARKETS_RESEARCH_TEMPLATE_ID",
    "GLOBAL_MARKETS_RESEARCH_TEMPLATE_VERSION",
    "GLOBAL_MARKETS_RESEARCH_TEMPLATE",
    "register_global_markets_research_prompts",
]

GLOBAL_MARKETS_RESEARCH_TEMPLATE_ID = "global_markets_research"
GLOBAL_MARKETS_RESEARCH_TEMPLATE_VERSION = 1

GLOBAL_MARKETS_RESEARCH_SYSTEM_PROMPT = """You are a market intelligence analyst assistant for MarketMind AI.

You must reason ONLY over the already-computed, ranked asset data supplied \
below. That ranking was produced by a fully deterministic pipeline — you \
must NEVER re-rank, re-score, or second-guess it, and NEVER invent a \
fact, price, event, or figure that is not directly present in the \
supplied data. This is not investment advice: never phrase any \
commentary as a recommendation to buy, sell, or hold.

Respond with a single JSON object matching exactly this shape, and \
nothing else (no markdown fences, no commentary outside the JSON):

{{
  "overall_summary": "<a concise synthesis of what this ranked list shows, in plain English>",
  "asset_commentaries": [
    {{"ticker": "<ticker>", "rank": <rank>, "commentary": "<a short, factor-grounded observation for this asset>"}}
  ],
  "risk_note": "<a short caveat about data completeness or freshness, or null if none>"
}}

Every "ticker"/"rank" pair in "asset_commentaries" MUST exactly match one \
of the ranked assets supplied below — never invent a ticker or a rank \
that was not given to you."""

GLOBAL_MARKETS_RESEARCH_USER_PROMPT = """Category: {category_display_name}
Market session: {session_summary}

Ranked assets (rank, ticker, final score, factor scores, freshness):
{ranked_assets_summary}

Using only the information above, produce the JSON analysis described in your instructions."""

GLOBAL_MARKETS_RESEARCH_TEMPLATE = PromptTemplate(
    template_id=GLOBAL_MARKETS_RESEARCH_TEMPLATE_ID,
    name="Global Markets Research",
    version=GLOBAL_MARKETS_RESEARCH_TEMPLATE_VERSION,
    description=(
        "Produces a grounded narrative interpretation of one main Global Market Intelligence "
        "category's already-ranked assets — never re-ranks, never invents facts."
    ),
    system_prompt=GLOBAL_MARKETS_RESEARCH_SYSTEM_PROMPT,
    user_prompt=GLOBAL_MARKETS_RESEARCH_USER_PROMPT,
)


def register_global_markets_research_prompts(registry: PromptRegistry) -> None:
    """Register the Global Markets Research template into `registry`.

    Raises:
        app.prompts.exceptions.TemplateAlreadyRegisteredError: If this
            exact (template_id, version) is already registered on `registry`.
    """
    registry.register(GLOBAL_MARKETS_RESEARCH_TEMPLATE)
