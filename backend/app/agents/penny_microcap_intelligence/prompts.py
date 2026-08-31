"""The Penny/Micro-cap Intelligence prompt template — registered via PromptRegistry.

Distinct from `app.agents.global_markets_research.prompts` in tone and
requirements only, not in mechanism: same grounding discipline (reason
only over supplied data, never re-rank, never invent), plus this
category's own explicit requirements — `risk_note` is REQUIRED (never
null, unlike the main-category template), and the system prompt
explicitly instructs the model that a risk classification is a
data-driven signal, never proof of fraud or manipulation (the same
terminology-careful framing `app.global_markets.ranking.classification`
already applies deterministically to `RiskClassification` itself — this
prompt extends the same discipline to the LLM's own prose).
"""

from __future__ import annotations

from app.prompts.registry import PromptRegistry
from app.prompts.template import PromptTemplate

__all__ = [
    "PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID",
    "PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_VERSION",
    "PENNY_MICROCAP_INTELLIGENCE_TEMPLATE",
    "register_penny_microcap_intelligence_prompts",
]

PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID = "penny_microcap_intelligence"
PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_VERSION = 1

PENNY_MICROCAP_INTELLIGENCE_SYSTEM_PROMPT = """You are a risk-conscious market intelligence \
analyst assistant for MarketMind AI, covering penny stocks and low-cap/micro-cap crypto — \
asset classes with materially higher volatility and lower data confidence than large, \
established markets.

You must reason ONLY over the already-computed, ranked asset data supplied \
below, including each asset's deterministic risk classification. That \
ranking and classification were produced by a fully deterministic \
pipeline — you must NEVER re-rank, re-score, or second-guess them, and \
NEVER invent a fact, price, event, or figure that is not directly present \
in the supplied data. This is not investment advice: never phrase any \
commentary as a recommendation to buy, sell, or hold.

A risk classification (e.g. "extreme risk") is a data-driven momentum/volatility \
signal ONLY — it is NEVER proof of fraud, manipulation, or wrongdoing, and you \
must never imply otherwise. Extreme momentum is not automatically dangerous, \
and moderate momentum is not automatically safe; describe what the data shows \
without moralizing about it.

Respond with a single JSON object matching exactly this shape, and \
nothing else (no markdown fences, no commentary outside the JSON):

{{
  "overall_summary": "<a concise synthesis of what this ranked list shows, in plain English>",
  "asset_commentaries": [
    {{"ticker": "<ticker>", "rank": <rank>, "commentary": "<a short, factor-grounded observation for this asset>"}}
  ],
  "risk_note": "<a REQUIRED, non-empty caveat covering data confidence, freshness, and volatility>"
}}

"risk_note" must never be null or empty for this category. Every \
"ticker"/"rank" pair in "asset_commentaries" MUST exactly match one of \
the ranked assets supplied below — never invent a ticker or a rank that \
was not given to you."""

PENNY_MICROCAP_INTELLIGENCE_USER_PROMPT = """Category: {category_display_name}
Market session: {session_summary}

Ranked assets (rank, ticker, final score, factor scores, risk classification, freshness):
{ranked_assets_summary}

Using only the information above, produce the JSON analysis described in your instructions."""

PENNY_MICROCAP_INTELLIGENCE_TEMPLATE = PromptTemplate(
    template_id=PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_ID,
    name="Penny/Micro-cap Intelligence",
    version=PENNY_MICROCAP_INTELLIGENCE_TEMPLATE_VERSION,
    description=(
        "Produces a grounded, risk-conscious narrative interpretation of one penny/micro-cap "
        "category's already-ranked, already-eligibility-filtered assets."
    ),
    system_prompt=PENNY_MICROCAP_INTELLIGENCE_SYSTEM_PROMPT,
    user_prompt=PENNY_MICROCAP_INTELLIGENCE_USER_PROMPT,
)


def register_penny_microcap_intelligence_prompts(registry: PromptRegistry) -> None:
    """Register the Penny/Micro-cap Intelligence template into `registry`.

    Raises:
        app.prompts.exceptions.TemplateAlreadyRegisteredError: If this
            exact (template_id, version) is already registered on `registry`.
    """
    registry.register(PENNY_MICROCAP_INTELLIGENCE_TEMPLATE)
