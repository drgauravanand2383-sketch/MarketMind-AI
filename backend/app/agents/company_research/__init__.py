"""CompanyResearchAgent (AGT-004): a deterministic structural report plus an
LLM-generated, evidence-grounded narrative (Sprint 39)."""

from app.agents.company_research.agent import (
    CompanyResearchAgent,
    CompanyResearchAgentError,
    LLMGenerationError,
    PromptRenderingError,
    ReportValidationError,
    ResponseParsingError,
)
from app.agents.company_research.models import (
    CompanyResearchNarrative,
    CompanyResearchReport,
    CompanyResearchRequest,
)
from app.agents.company_research.prompts import (
    COMPANY_RESEARCH_TEMPLATE,
    COMPANY_RESEARCH_TEMPLATE_ID,
    register_company_research_prompts,
)

__all__ = [
    "CompanyResearchAgent",
    "CompanyResearchAgentError",
    "PromptRenderingError",
    "LLMGenerationError",
    "ResponseParsingError",
    "ReportValidationError",
    "CompanyResearchRequest",
    "CompanyResearchReport",
    "CompanyResearchNarrative",
    "COMPANY_RESEARCH_TEMPLATE",
    "COMPANY_RESEARCH_TEMPLATE_ID",
    "register_company_research_prompts",
]
