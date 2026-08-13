"""Integration tests: StructuredOutputParser + OutputValidator working
together via OutputValidator.process()."""

from __future__ import annotations

import pytest

from app.services.guardrails.exceptions import ParsingError, ValidationError
from app.services.guardrails.models import GuardrailRequest
from app.services.guardrails.validator import OutputValidator
from tests.services.guardrails.conftest import Address, Person


@pytest.fixture
def validator() -> OutputValidator:
    return OutputValidator()


# --- Parser + validator -----------------------------------------------------------


def test_process_parses_and_validates_clean_json(validator: OutputValidator) -> None:
    raw = '{"city": "Paris", "zip_code": "75000"}'

    result = validator.process(GuardrailRequest(raw_response=raw, expected_schema=Address))

    assert result.success is True
    assert result.parsed_object.city == "Paris"
    assert result.repaired is False


def test_process_parses_and_validates_nested_json(validator: OutputValidator) -> None:
    raw = '{"name": "Ada", "age": 30, "address": {"city": "London", "zip_code": "SW1"}}'

    result = validator.process(GuardrailRequest(raw_response=raw, expected_schema=Person))

    assert result.success is True
    assert result.parsed_object.address.city == "London"


# --- Repaired output -----------------------------------------------------------


def test_process_repairs_markdown_fenced_json_before_validating(validator: OutputValidator) -> None:
    raw = '```json\n{"city": "Paris", "zip_code": "75000"}\n```'

    result = validator.process(GuardrailRequest(raw_response=raw, expected_schema=Address))

    assert result.success is True
    assert result.repaired is True
    assert any("code fence" in warning.lower() for warning in result.warnings)


def test_process_repairs_whitespace_and_line_endings_before_validating(
    validator: OutputValidator,
) -> None:
    raw = '  \r\n {"city": "Paris", "zip_code": "75000"}  \r\n  '

    result = validator.process(GuardrailRequest(raw_response=raw, expected_schema=Address))

    assert result.success is True
    assert result.repaired is True


def test_process_reports_repaired_true_even_when_validation_still_fails(
    validator: OutputValidator,
) -> None:
    """Repair happens before validation and is independent of its outcome —
    a well-formatted-but-incomplete document is still reported as repaired."""
    raw = '```json\n{"city": "Paris"}\n```'  # missing zip_code

    result = validator.process(GuardrailRequest(raw_response=raw, expected_schema=Address))

    assert result.success is False
    assert result.repaired is True


# --- Failed output -----------------------------------------------------------


def test_process_reports_parsing_failure_as_a_validation_error() -> None:
    validator = OutputValidator()
    result = validator.process(
        GuardrailRequest(raw_response="not valid json{{{", expected_schema=Address)
    )

    assert result.success is False
    assert result.parsed_object is None
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field is None


def test_process_reports_schema_failure_with_field_level_detail() -> None:
    validator = OutputValidator()
    result = validator.process(
        GuardrailRequest(raw_response='{"city": "Paris"}', expected_schema=Address)
    )

    assert result.success is False
    assert any(issue.field == "zip_code" for issue in result.validation_errors)


def test_process_strict_mode_raises_parsing_error_for_malformed_json() -> None:
    validator = OutputValidator()
    with pytest.raises(ParsingError):
        validator.process(
            GuardrailRequest(raw_response="not json", expected_schema=Address), strict=True
        )


def test_process_strict_mode_raises_validation_error_for_schema_mismatch() -> None:
    validator = OutputValidator()
    with pytest.raises(ValidationError):
        validator.process(
            GuardrailRequest(raw_response='{"city": "Paris"}', expected_schema=Address), strict=True
        )


# --- Dependency injection -----------------------------------------------------------


def test_validator_uses_its_injected_parser() -> None:
    from app.services.guardrails.parser import StructuredOutputParser

    custom_parser = StructuredOutputParser()
    validator = OutputValidator(parser=custom_parser)

    assert validator._parser is custom_parser


def test_two_validators_constructed_independently_do_not_share_state() -> None:
    validator_a = OutputValidator()
    validator_b = OutputValidator()

    assert validator_a is not validator_b
    assert validator_a._parser is not validator_b._parser
