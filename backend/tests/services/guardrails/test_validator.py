"""Tests for OutputValidator (app.services.guardrails.validator)."""

from __future__ import annotations

import pytest

from app.services.guardrails.exceptions import ValidationError
from app.services.guardrails.validator import OutputValidator
from tests.services.guardrails.conftest import Address, Person


@pytest.fixture
def validator() -> OutputValidator:
    return OutputValidator()


# --- Success -----------------------------------------------------------


def test_valid_data_validates_successfully(validator: OutputValidator) -> None:
    data = {"name": "Ada", "age": 30, "address": {"city": "London", "zip_code": "SW1"}}

    result = validator.validate(data, Person)

    assert result.success is True
    assert isinstance(result.parsed_object, Person)
    assert result.parsed_object.name == "Ada"
    assert result.validation_errors == []


def test_simple_schema_without_nesting_validates_successfully(validator: OutputValidator) -> None:
    result = validator.validate({"city": "Paris", "zip_code": "75000"}, Address)
    assert result.success is True
    assert result.parsed_object.city == "Paris"


# --- Missing field -----------------------------------------------------------


def test_missing_required_field_is_reported() -> None:
    validator = OutputValidator()
    data = {"name": "Ada", "address": {"city": "London", "zip_code": "SW1"}}  # missing age

    result = validator.validate(data, Person)

    assert result.success is False
    assert result.parsed_object is None
    assert any(issue.field == "age" for issue in result.validation_errors)
    assert all(issue.severity == "error" for issue in result.validation_errors)


def test_missing_field_error_message_is_descriptive() -> None:
    validator = OutputValidator()
    result = validator.validate({}, Address)

    fields = {issue.field for issue in result.validation_errors}
    assert fields == {"city", "zip_code"}
    assert all(issue.message for issue in result.validation_errors)


# --- Wrong type -----------------------------------------------------------


def test_wrong_type_is_reported() -> None:
    validator = OutputValidator()
    data = {"name": "Ada", "age": "not a number", "address": {"city": "London", "zip_code": "SW1"}}

    result = validator.validate(data, Person)

    assert result.success is False
    age_issue = next(issue for issue in result.validation_errors if issue.field == "age")
    assert "valid integer" in age_issue.message.lower() or "int" in age_issue.message.lower()


def test_non_dict_input_is_reported_not_raised() -> None:
    validator = OutputValidator()
    result = validator.validate([1, 2, 3], Person)
    assert result.success is False
    assert result.validation_errors != []


# --- Extra field -----------------------------------------------------------


def test_extra_field_is_rejected_when_schema_forbids_extras() -> None:
    validator = OutputValidator()
    data = {"city": "Paris", "zip_code": "75000", "country": "France"}

    result = validator.validate(data, Address)

    assert result.success is False
    assert any(issue.field == "country" for issue in result.validation_errors)


# --- Nested validation -----------------------------------------------------------


def test_nested_validation_error_reports_the_full_field_path() -> None:
    validator = OutputValidator()
    data = {"name": "Ada", "age": 30, "address": {"city": "London"}}  # missing zip_code

    result = validator.validate(data, Person)

    assert result.success is False
    assert any(issue.field == "address.zip_code" for issue in result.validation_errors)


def test_nested_wrong_type_reports_the_full_field_path() -> None:
    validator = OutputValidator()
    data = {"name": "Ada", "age": 30, "address": {"city": "London", "zip_code": 12345}}

    result = validator.validate(data, Person)

    assert result.success is False
    assert any(issue.field == "address.zip_code" for issue in result.validation_errors)


def test_deeply_nested_missing_field_reports_full_path() -> None:
    validator = OutputValidator()
    data = {"name": "Ada", "age": 30, "address": {}}

    result = validator.validate(data, Person)

    fields = {issue.field for issue in result.validation_errors}
    assert "address.city" in fields
    assert "address.zip_code" in fields


# --- Strict mode -----------------------------------------------------------


def test_strict_mode_raises_instead_of_returning_a_failed_result() -> None:
    validator = OutputValidator()
    with pytest.raises(ValidationError):
        validator.validate({}, Address, strict=True)


def test_non_strict_mode_never_raises_for_ordinary_invalid_data() -> None:
    validator = OutputValidator()
    result = validator.validate({}, Address, strict=False)
    assert result.success is False  # returned, not raised


def test_strict_mode_does_not_raise_on_success() -> None:
    validator = OutputValidator()
    result = validator.validate({"city": "Paris", "zip_code": "75000"}, Address, strict=True)
    assert result.success is True
