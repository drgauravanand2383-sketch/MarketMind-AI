"""Tests for the Guardrails Framework's typed models (app.services.guardrails.models)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.services.guardrails.models import GuardrailRequest, GuardrailResult, ValidationIssue
from tests.services.guardrails.conftest import Address


def test_validation_issue_defaults_to_error_severity() -> None:
    issue = ValidationIssue(message="bad")
    assert issue.severity == "error"
    assert issue.field is None


def test_validation_issue_rejects_unknown_severity() -> None:
    with pytest.raises(PydanticValidationError):
        ValidationIssue(message="bad", severity="critical")  # type: ignore[arg-type]


def test_guardrail_request_holds_the_expected_schema_class() -> None:
    request = GuardrailRequest(raw_response="{}", expected_schema=Address)
    assert request.expected_schema is Address
    assert request.metadata == {}


def test_guardrail_request_accepts_metadata() -> None:
    request = GuardrailRequest(raw_response="{}", expected_schema=Address, metadata={"trace_id": "x"})
    assert request.metadata == {"trace_id": "x"}


def test_guardrail_result_defaults() -> None:
    result = GuardrailResult(success=True)
    assert result.parsed_object is None
    assert result.validation_errors == []
    assert result.warnings == []
    assert result.repaired is False


def test_guardrail_request_extra_fields_rejected() -> None:
    with pytest.raises(PydanticValidationError):
        GuardrailRequest(raw_response="{}", expected_schema=Address, unexpected_field="x")
