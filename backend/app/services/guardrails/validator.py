"""OutputValidator — validates parsed data against a Pydantic schema.

No AI calls, no prompt rendering, no repository logic — pure schema
validation, producing typed `ValidationIssue` objects rather than raising,
by default. `process()` combines this with `StructuredOutputParser` for
the full parse-then-validate pipeline agents will use as their standard
LLM-response post-processing layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.services.guardrails.exceptions import ParsingError, ValidationError
from app.services.guardrails.models import GuardrailRequest, GuardrailResult, ValidationIssue
from app.services.guardrails.parser import StructuredOutputParser

__all__ = ["OutputValidator"]


class OutputValidator:
    """Validates data against a Pydantic schema.

    No singleton, no global state: construct one instance and inject it
    wherever LLM output needs validating.
    """

    def __init__(self, parser: StructuredOutputParser | None = None) -> None:
        """Initialize with the parser `process()` delegates to.

        Args:
            parser: Defaults to a fresh `StructuredOutputParser` — pass
                one explicitly only if a caller needs a customized parser.
        """
        self._parser = parser if parser is not None else StructuredOutputParser()

    def validate(
        self, data: Any, expected_schema: type[BaseModel], *, strict: bool = False
    ) -> GuardrailResult:
        """Validate `data` against `expected_schema`.

        Args:
            data: Already-parsed data (e.g. a dict from `StructuredOutputParser`).
            expected_schema: The Pydantic model class `data` must satisfy.
                Unknown fields are rejected exactly when `expected_schema`
                itself is configured with `extra="forbid"` — this method
                adds no additional restriction of its own; required-field
                and type checks are likewise entirely `expected_schema`'s
                own, including for nested sub-models.
            strict: If True, raise `ValidationError` on failure instead of
                returning a `GuardrailResult` with `success=False`.

        Returns:
            A GuardrailResult. `parsed_object` is the validated
            `expected_schema` instance on success, else `None`.

        Raises:
            ValidationError: Only if `strict=True` and validation fails.
        """
        try:
            instance = expected_schema.model_validate(data)
        except PydanticValidationError as exc:
            issues = [self._to_issue(error) for error in exc.errors()]
            if strict:
                raise ValidationError(
                    f"Validation failed for {expected_schema.__name__}: {issues[0].message}",
                    field=issues[0].field,
                ) from exc
            return GuardrailResult(
                success=False, parsed_object=None, validation_errors=issues, warnings=[], repaired=False
            )

        return GuardrailResult(
            success=True, parsed_object=instance, validation_errors=[], warnings=[], repaired=False
        )

    def process(self, request: GuardrailRequest, *, strict: bool = False) -> GuardrailResult:
        """The full pipeline: safely parse `request.raw_response`, then validate it.

        Raises:
            ParsingError: Only if `strict=True` and parsing fails.
            ValidationError: Only if `strict=True` and validation fails.
        """
        outcome = self._parser.parse(request.raw_response)
        if outcome.error is not None:
            if strict:
                raise ParsingError(outcome.error)
            return GuardrailResult(
                success=False,
                parsed_object=None,
                validation_errors=[ValidationIssue(field=None, severity="error", message=outcome.error)],
                warnings=outcome.warnings,
                repaired=outcome.repaired,
            )

        result = self.validate(outcome.value, request.expected_schema, strict=strict)
        return result.model_copy(
            update={
                "warnings": [*outcome.warnings, *result.warnings],
                "repaired": outcome.repaired,
            }
        )

    @staticmethod
    def _to_issue(error: dict[str, Any]) -> ValidationIssue:
        loc = error.get("loc", ())
        field = ".".join(str(part) for part in loc) if loc else None
        return ValidationIssue(field=field, severity="error", message=error["msg"])
