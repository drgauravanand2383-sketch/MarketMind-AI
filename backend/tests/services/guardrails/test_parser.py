"""Tests for StructuredOutputParser (app.services.guardrails.parser)."""

from __future__ import annotations

import pytest

from app.services.guardrails.exceptions import RepairError
from app.services.guardrails.parser import StructuredOutputParser


@pytest.fixture
def parser() -> StructuredOutputParser:
    return StructuredOutputParser()


# --- Valid JSON -----------------------------------------------------------


def test_valid_json_parses_successfully(parser: StructuredOutputParser) -> None:
    outcome = parser.parse('{"a": 1, "b": "text"}')

    assert outcome.error is None
    assert outcome.value == {"a": 1, "b": "text"}
    assert outcome.repaired is False


def test_valid_json_array_parses_successfully(parser: StructuredOutputParser) -> None:
    outcome = parser.parse("[1, 2, 3]")
    assert outcome.error is None
    assert outcome.value == [1, 2, 3]


# --- Invalid JSON -----------------------------------------------------------


def test_invalid_json_returns_an_error_not_a_raise(parser: StructuredOutputParser) -> None:
    outcome = parser.parse("not valid json{{{")

    assert outcome.error is not None
    assert outcome.value is None


def test_empty_string_returns_an_error(parser: StructuredOutputParser) -> None:
    outcome = parser.parse("")
    assert outcome.error is not None


def test_truncated_json_returns_an_error(parser: StructuredOutputParser) -> None:
    outcome = parser.parse('{"a": 1, "b":')
    assert outcome.error is not None


# --- Markdown-fenced JSON -----------------------------------------------------------


def test_markdown_fenced_json_is_unwrapped_and_parsed() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('```json\n{"a": 1}\n```')

    assert outcome.error is None
    assert outcome.value == {"a": 1}
    assert outcome.repaired is True
    assert any("code fence" in warning.lower() for warning in outcome.warnings)


def test_markdown_fenced_json_without_language_tag() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('```\n{"a": 1}\n```')

    assert outcome.error is None
    assert outcome.value == {"a": 1}


# --- Whitespace -----------------------------------------------------------


def test_leading_and_trailing_whitespace_is_trimmed() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('   \n  {"a": 1}  \n  ')

    assert outcome.error is None
    assert outcome.value == {"a": 1}
    assert outcome.repaired is True
    assert any("whitespace" in warning.lower() for warning in outcome.warnings)


def test_windows_line_endings_are_normalized() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{\r\n  "a": 1\r\n}')

    assert outcome.error is None
    assert outcome.value == {"a": 1}
    assert outcome.repaired is True
    assert any("line ending" in warning.lower() for warning in outcome.warnings)


def test_well_formed_input_reports_no_repair() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"a": 1}')
    assert outcome.repaired is False
    assert outcome.warnings == []


# --- Malformed objects -----------------------------------------------------------


def test_trailing_comma_is_not_repaired_and_fails_to_parse() -> None:
    """A trailing comma is a common LLM mistake, but fixing it isn't one of
    the three sanctioned repairs — it must remain a genuine parse error."""
    parser = StructuredOutputParser()
    outcome = parser.parse('{"a": 1,}')
    assert outcome.error is not None


def test_single_quoted_keys_are_not_repaired_and_fail_to_parse() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse("{'a': 1}")
    assert outcome.error is not None


def test_unterminated_string_fails_to_parse() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"a": "unterminated}')
    assert outcome.error is not None


# --- Duplicate keys -----------------------------------------------------------


def test_duplicate_key_is_rejected_by_default() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"a": 1, "a": 2}')
    assert outcome.error is not None
    assert "duplicate" in outcome.error.lower()


def test_nested_duplicate_key_is_rejected() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"outer": {"a": 1, "a": 2}}')
    assert outcome.error is not None


def test_duplicate_key_rejection_can_be_disabled() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"a": 1, "a": 2}', reject_duplicate_keys=False)
    assert outcome.error is None
    assert outcome.value == {"a": 2}  # standard json.loads behavior: last one wins


# --- Type preservation -----------------------------------------------------------


def test_numeric_and_string_types_are_preserved() -> None:
    parser = StructuredOutputParser()
    outcome = parser.parse('{"int": 1, "float": 1.5, "str": "1", "bool": true, "null": null}')

    assert outcome.value["int"] == 1 and isinstance(outcome.value["int"], int)
    assert outcome.value["float"] == 1.5 and isinstance(outcome.value["float"], float)
    assert outcome.value["str"] == "1" and isinstance(outcome.value["str"], str)
    assert outcome.value["bool"] is True
    assert outcome.value["null"] is None


# --- RepairError -----------------------------------------------------------


def test_non_string_input_raises_repair_error() -> None:
    parser = StructuredOutputParser()
    with pytest.raises(RepairError):
        parser.parse(None)  # type: ignore[arg-type]
