"""The Company Research prompt template — registered via PromptRegistry.

Contains no reasoning of its own: this module only defines the
declarative `PromptTemplate` (system/user prompt text with placeholders)
`CompanyResearchAgent` renders and sends to `LLMService`. The actual
analysis happens inside the LLM, grounded entirely in the evidence text
this template's placeholders receive — never hardcoded into the agent.

Per `app.prompts.registry.PromptRegistry`'s own contract, this template is
never auto-discovered: `register_company_research_prompts()` must be
called explicitly, with an already-constructed `PromptRegistry`, before
that registry is injected into `CompanyResearchAgent`.
"""

from __future__ import annotations

from app.prompts.registry import PromptRegistry
from app.prompts.template import PromptTemplate

__all__ = [
    "COMPANY_RESEARCH_TEMPLATE_ID",
    "COMPANY_RESEARCH_TEMPLATE_VERSION",
    "COMPANY_RESEARCH_TEMPLATE",
    "register_company_research_prompts",
]

COMPANY_RESEARCH_TEMPLATE_ID = "company_research"
COMPANY_RESEARCH_TEMPLATE_VERSION = 1

COMPANY_RESEARCH_SYSTEM_PROMPT = """You are a financial research analyst assistant.

You must reason ONLY over the evidence, relationships, and market \
intelligence supplied to you below. Do not invent, assume, or infer any \
fact that is not directly supported by the supplied evidence. If the \
evidence is insufficient to support a statement, say so explicitly \
rather than guessing.

Respond with a single JSON object matching exactly this shape, and \
nothing else (no markdown fences, no commentary outside the JSON):

{{
  "summary": "<a concise, evidence-grounded analysis of the company>",
  "key_findings": ["<finding 1>", "<finding 2>"],
  "risk_commentary": "<a short evidence-grounded risk note, or null if none>"
}}"""

COMPANY_RESEARCH_USER_PROMPT = """Company: {company_name}

Retrieved evidence:
{evidence_summary}

Relationships:
{relationship_summary}

Market intelligence:
{market_intelligence_summary}

Using only the information above, produce the JSON analysis described in your instructions."""

COMPANY_RESEARCH_TEMPLATE = PromptTemplate(
    template_id=COMPANY_RESEARCH_TEMPLATE_ID,
    name="Company Research",
    version=COMPANY_RESEARCH_TEMPLATE_VERSION,
    description=(
        "Produces an evidence-grounded narrative analysis for one company, given "
        "retrieved evidence, relationships, and market intelligence."
    ),
    system_prompt=COMPANY_RESEARCH_SYSTEM_PROMPT,
    user_prompt=COMPANY_RESEARCH_USER_PROMPT,
)


def register_company_research_prompts(registry: PromptRegistry) -> None:
    """Register the Company Research template into `registry`.

    Raises:
        app.prompts.exceptions.TemplateAlreadyRegisteredError: If this
            exact (template_id, version) is already registered on
            `registry` — calling this twice on the same registry is not
            idempotent, matching PromptRegistry's own explicit
            duplicate-prevention contract.
    """
    registry.register(COMPANY_RESEARCH_TEMPLATE)
