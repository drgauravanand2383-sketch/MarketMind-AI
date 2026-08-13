"""Tests for PromptTemplate (app.prompts.template)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.prompts.exceptions import TemplateValidationError
from app.prompts.models import PromptMetadata
from app.prompts.template import PromptTemplate
from tests.prompts.conftest import build_template

# --- Creation -----------------------------------------------------------


def test_template_creation_succeeds_with_valid_fields() -> None:
    template = build_template()
    assert template.template_id == "company_research"
    assert template.name == "Company Research"
    assert template.version == 1
    assert template.description == "Research a company"


def test_template_is_frozen() -> None:
    template = build_template()
    with pytest.raises(ValidationError):
        template.name = "changed"


def test_template_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            template_id="x",
            name="x",
            version=1,
            description="x",
            system_prompt="hi",
            user_prompt="hi",
            unexpected_field="x",
        )


# --- Validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["template_id", "name", "description", "system_prompt", "user_prompt"]
)
def test_template_rejects_empty_required_string_fields(field: str) -> None:
    kwargs = {
        "template_id": "x",
        "name": "x",
        "version": 1,
        "description": "x",
        "system_prompt": "hi",
        "user_prompt": "hi",
    }
    kwargs[field] = ""
    with pytest.raises(ValidationError):
        PromptTemplate(**kwargs)


def test_template_version_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        build_template(version=0)


def test_template_rejects_unnamed_placeholder() -> None:
    with pytest.raises(TemplateValidationError):
        build_template(system_prompt="Hello {}", user_prompt="hi")


def test_template_rejects_positional_placeholder() -> None:
    with pytest.raises(TemplateValidationError):
        build_template(system_prompt="Hello {0}", user_prompt="hi")


def test_template_rejects_attribute_access_placeholder() -> None:
    with pytest.raises(TemplateValidationError):
        build_template(system_prompt="Hello {a.b}", user_prompt="hi")


def test_template_accepts_placeholder_with_format_spec() -> None:
    template = build_template(system_prompt="Count: {count:03d}", user_prompt="hi")
    assert template.required_variables == frozenset({"count"})


def test_template_accepts_placeholder_with_conversion() -> None:
    template = build_template(system_prompt="Name: {name!r}", user_prompt="hi")
    assert template.required_variables == frozenset({"name"})


# --- Required variables -----------------------------------------------------------


def test_required_variables_derived_from_both_prompts() -> None:
    template = build_template(
        system_prompt="System needs {a}.", user_prompt="User needs {b} and {c}."
    )
    assert template.required_variables == frozenset({"a", "b", "c"})


def test_required_variables_deduplicates_repeated_placeholders() -> None:
    template = build_template(
        system_prompt="Hello {name}.", user_prompt="{name}, is {name} your real name?"
    )
    assert template.required_variables == frozenset({"name"})


def test_required_variables_empty_when_no_placeholders() -> None:
    template = build_template(system_prompt="Static system prompt.", user_prompt="Static user prompt.")
    assert template.required_variables == frozenset()


# --- Metadata -----------------------------------------------------------


def test_template_metadata_returns_prompt_metadata() -> None:
    template = build_template()
    metadata = template.metadata

    assert isinstance(metadata, PromptMetadata)
    assert metadata.template_id == "company_research"
    assert metadata.name == "Company Research"
    assert metadata.version == 1
    assert metadata.description == "Research a company"
    assert metadata.required_variables == ("company_name", "sector")


def test_template_metadata_never_includes_prompt_text() -> None:
    metadata = build_template().metadata
    assert not hasattr(metadata, "system_prompt")
    assert not hasattr(metadata, "user_prompt")
