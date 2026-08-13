"""Tests for PromptRenderer (app.prompts.renderer).

Exercises `render_template()` directly against a PromptTemplate — no
PromptRegistry involvement here (see test_integration.py for the
registry + renderer combination).
"""

from __future__ import annotations

import pytest

from app.prompts.exceptions import MissingVariablesError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from tests.prompts.conftest import build_template


def _renderer() -> PromptRenderer:
    """render_template() never touches the registry, so an empty one is fine here."""
    return PromptRenderer(PromptRegistry())


# --- Successful rendering -----------------------------------------------------------


def test_successful_rendering_substitutes_all_variables() -> None:
    template = build_template(
        system_prompt="You research {sector} companies.",
        user_prompt="Research {company_name} in the {sector} sector.",
    )

    result = _renderer().render_template(template, {"company_name": "Acme", "sector": "Tech"})

    assert result.system_prompt == "You research Tech companies."
    assert result.user_prompt == "Research Acme in the Tech sector."


def test_successful_rendering_returns_template_id_and_version() -> None:
    template = build_template(version=3)
    result = _renderer().render_template(
        template, {"company_name": "Acme", "sector": "Tech"}
    )
    assert result.template_id == "company_research"
    assert result.version == 3


def test_successful_rendering_with_no_placeholders_at_all() -> None:
    template = build_template(system_prompt="Static.", user_prompt="Also static.")
    result = _renderer().render_template(template, {})
    assert result.system_prompt == "Static."
    assert result.user_prompt == "Also static."
    assert result.variables_used == ()


# --- Missing variables -----------------------------------------------------------


def test_missing_variables_raises() -> None:
    template = build_template()  # needs company_name and sector

    with pytest.raises(MissingVariablesError):
        _renderer().render_template(template, {"company_name": "Acme"})


def test_missing_variables_error_reports_the_missing_names() -> None:
    template = build_template()

    with pytest.raises(MissingVariablesError) as excinfo:
        _renderer().render_template(template, {})

    assert excinfo.value.missing_variables == frozenset({"company_name", "sector"})
    assert excinfo.value.template_id == "company_research"


# --- Extra variables -----------------------------------------------------------


def test_extra_variables_are_ignored_not_rejected() -> None:
    template = build_template()

    result = _renderer().render_template(
        template, {"company_name": "Acme", "sector": "Tech", "unused": "ignored"}
    )

    assert result.user_prompt == "Research the company Acme in the Tech sector."
    assert "unused" not in result.variables_used


# --- Repeated placeholders -----------------------------------------------------------


def test_repeated_placeholder_substitutes_every_occurrence() -> None:
    template = build_template(
        system_prompt="You are researching {company_name}.",
        user_prompt="{company_name} is a company. Tell me about {company_name}.",
    )

    result = _renderer().render_template(template, {"company_name": "Acme"})

    assert result.user_prompt == "Acme is a company. Tell me about Acme."
    assert result.variables_used == ("company_name",)


# --- Multiline prompts -----------------------------------------------------------


def test_multiline_prompt_renders_correctly() -> None:
    template = build_template(
        system_prompt="You are a research assistant.\nBe concise.\nCite sources.",
        user_prompt="Research {company_name}.\n\nFocus on:\n- Revenue\n- {sector} position",
    )

    result = _renderer().render_template(template, {"company_name": "Acme", "sector": "Tech"})

    assert result.system_prompt == "You are a research assistant.\nBe concise.\nCite sources."
    assert result.user_prompt == "Research Acme.\n\nFocus on:\n- Revenue\n- Tech position"


# --- variables_used -----------------------------------------------------------


def test_variables_used_reflects_required_variables_sorted() -> None:
    template = build_template(
        system_prompt="{zebra} and {apple}.", user_prompt="Static user prompt."
    )

    result = _renderer().render_template(template, {"zebra": "z", "apple": "a"})

    assert result.variables_used == ("apple", "zebra")
