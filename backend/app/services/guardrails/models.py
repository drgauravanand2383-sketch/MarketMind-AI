"""Typed models for the Guardrails Framework.

`GuardrailRequest`/`GuardrailResult`/`ValidationIssue` are the framework's
public request/response shapes. `ParseOutcome` is an internal, supporting
type — `StructuredOutputParser`'s own return shape, consumed by
`OutputValidator.process()` and not usually constructed directly by
callers outside this package.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ValidationIssue", "GuardrailRequest", "GuardrailResult", "ParseOutcome"]


class ValidationIssue(BaseModel):
    """One validation problem, at a specific field path (or `None` for a
    document-level issue, e.g. malformed JSON with no field to point to)."""

    model_config = ConfigDict(extra="forbid")

    field: str | None = None
    severity: Literal["error", "warning"] = "error"
    message: str


class GuardrailRequest(BaseModel):
    """A request to `OutputValidator.process()`."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    raw_response: str
    expected_schema: type[BaseModel]
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailResult(BaseModel):
    """The outcome of validating (and, if needed, repairing) one LLM response.

    `parsed_object` is the validated `expected_schema` instance on
    success, else `None`. `repaired` is `True` if `StructuredOutputParser`
    applied any of its three sanctioned repairs to the raw text, whether
    or not validation ultimately succeeded.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    success: bool
    parsed_object: BaseModel | None = None
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repaired: bool = False


class ParseOutcome(BaseModel):
    """`StructuredOutputParser.parse()`'s own result — a pre-validation outcome.

    Not part of this framework's primary 3-model public surface
    (`GuardrailRequest`/`GuardrailResult`/`ValidationIssue`), but a small
    supporting type `OutputValidator` consumes internally.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    value: Any = None
    repaired: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
