"""Guardrails Framework — validates, repairs, and safely parses LLM
responses before they reach any agent.

`StructuredOutputParser` (parser.py) repairs raw text with three safe,
content-preserving transformations and parses it as JSON — never
inventing or inferring content. `OutputValidator` (validator.py) validates
parsed data against a Pydantic schema, producing typed `ValidationIssue`
objects rather than raising by default (an optional strict mode raises
instead). No AI calls, no prompt rendering, no repository logic anywhere
in this package.

This sprint introduces the framework itself; no existing agent has been
modified to use it yet — future LLM-powered agents are expected to route
their LLM responses through `OutputValidator.process()` as their standard
post-processing layer.
"""

from app.services.guardrails.exceptions import (
    GuardrailError,
    ParsingError,
    RepairError,
    ValidationError,
)
from app.services.guardrails.models import (
    GuardrailRequest,
    GuardrailResult,
    ParseOutcome,
    ValidationIssue,
)
from app.services.guardrails.parser import StructuredOutputParser
from app.services.guardrails.validator import OutputValidator

__all__ = [
    "ValidationIssue",
    "GuardrailRequest",
    "GuardrailResult",
    "ParseOutcome",
    "StructuredOutputParser",
    "OutputValidator",
    "GuardrailError",
    "ParsingError",
    "ValidationError",
    "RepairError",
]
