"""The Portfolio Intelligence prompt template — registered via PromptRegistry.

Contains no reasoning of its own: this module only defines the
declarative `PromptTemplate` (system/user prompt text with placeholders)
`PortfolioIntelligenceAgent` renders and sends to `LLMService`. The actual
analysis happens inside the LLM, grounded entirely in the portfolio data,
evidence, and relationships this template's placeholders receive — never
hardcoded into the agent, and never an investment recommendation.

Per `app.prompts.registry.PromptRegistry`'s own contract, this template is
never auto-discovered: `register_portfolio_intelligence_prompts()` must be
called explicitly, with an already-constructed `PromptRegistry`, before
that registry is injected into `PortfolioIntelligenceAgent`.
"""

from __future__ import annotations

from app.prompts.registry import PromptRegistry
from app.prompts.template import PromptTemplate

__all__ = [
    "PORTFOLIO_INTELLIGENCE_TEMPLATE_ID",
    "PORTFOLIO_INTELLIGENCE_TEMPLATE_VERSION",
    "PORTFOLIO_INTELLIGENCE_TEMPLATE",
    "register_portfolio_intelligence_prompts",
]

PORTFOLIO_INTELLIGENCE_TEMPLATE_ID = "portfolio_intelligence"
PORTFOLIO_INTELLIGENCE_TEMPLATE_VERSION = 1

PORTFOLIO_INTELLIGENCE_SYSTEM_PROMPT = """You are a portfolio research analyst assistant.

You must reason ONLY over the portfolio data, evidence, and relationships \
supplied to you below. Do not invent, assume, or infer any fact that is \
not directly supported by the supplied information. If the evidence is \
insufficient to support a statement, say so explicitly rather than \
guessing.

You must NEVER provide an investment recommendation, a buy/sell/hold \
recommendation, or a price target of any kind, for the portfolio or any \
individual holding. This is a research summary only, not investment \
advice.

Respond with a single JSON object matching exactly this shape, and \
nothing else (no markdown fences, no commentary outside the JSON):

{{
  "executive_summary": "<a concise, evidence-grounded overview of the portfolio>",
  "concentration_observations": ["<observation 1>", "<observation 2>"],
  "relationship_observations": ["<observation 1>", "<observation 2>"],
  "notable_market_events": ["<event 1>", "<event 2>"]
}}"""

PORTFOLIO_INTELLIGENCE_USER_PROMPT = """Portfolio: {portfolio_name}

Company summaries:
{company_summaries}

Sector exposure:
{sector_exposure_summary}

Relationships among portfolio holdings:
{shared_relationship_summary}

Broader relationships detected across portfolio evidence:
{portfolio_relationship_summary}

Supporting evidence:
{evidence_summary}

User notes:
{user_notes}

Using only the information above, produce the JSON analysis described in your instructions."""

PORTFOLIO_INTELLIGENCE_TEMPLATE = PromptTemplate(
    template_id=PORTFOLIO_INTELLIGENCE_TEMPLATE_ID,
    name="Portfolio Intelligence",
    version=PORTFOLIO_INTELLIGENCE_TEMPLATE_VERSION,
    description=(
        "Produces an evidence-grounded narrative analysis for a portfolio of companies, "
        "given per-company research, sector exposure, relationships, and evidence. "
        "Never an investment recommendation."
    ),
    system_prompt=PORTFOLIO_INTELLIGENCE_SYSTEM_PROMPT,
    user_prompt=PORTFOLIO_INTELLIGENCE_USER_PROMPT,
)


def register_portfolio_intelligence_prompts(registry: PromptRegistry) -> None:
    """Register the Portfolio Intelligence template into `registry`.

    Raises:
        app.prompts.exceptions.TemplateAlreadyRegisteredError: If this
            exact (template_id, version) is already registered on
            `registry` — calling this twice on the same registry is not
            idempotent, matching PromptRegistry's own explicit
            duplicate-prevention contract.
    """
    registry.register(PORTFOLIO_INTELLIGENCE_TEMPLATE)
