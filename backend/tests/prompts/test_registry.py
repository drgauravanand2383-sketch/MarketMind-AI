"""Tests for PromptRegistry (app.prompts.registry)."""

from __future__ import annotations

import pytest

from app.prompts.exceptions import TemplateAlreadyRegisteredError, TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from tests.prompts.conftest import build_template

# --- Registration -----------------------------------------------------------


def test_register_and_get_returns_the_template() -> None:
    registry = PromptRegistry()
    template = build_template()

    registry.register(template)

    assert registry.get("company_research") is template


def test_register_different_template_ids_coexist() -> None:
    registry = PromptRegistry()
    registry.register(build_template(template_id="a"))
    registry.register(build_template(template_id="b"))

    assert registry.get("a").template_id == "a"
    assert registry.get("b").template_id == "b"


# --- Duplicate prevention -----------------------------------------------------------


def test_register_duplicate_template_id_and_version_raises() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=1))

    with pytest.raises(TemplateAlreadyRegisteredError):
        registry.register(build_template(version=1))


def test_register_same_template_id_different_version_is_allowed() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=1))
    registry.register(build_template(version=2))

    assert registry.list_versions("company_research") == (1, 2)


def test_duplicate_registration_does_not_replace_existing_template() -> None:
    registry = PromptRegistry()
    first = build_template(version=1, description="first")
    registry.register(first)

    try:
        registry.register(build_template(version=1, description="second"))
    except TemplateAlreadyRegisteredError:
        pass

    assert registry.get("company_research", 1).description == "first"


# --- Latest version -----------------------------------------------------------


def test_get_without_version_returns_latest() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=1, description="v1"))
    registry.register(build_template(version=3, description="v3"))
    registry.register(build_template(version=2, description="v2"))

    assert registry.get("company_research").version == 3
    assert registry.get("company_research").description == "v3"


# --- Specific version -----------------------------------------------------------


def test_get_specific_version_returns_that_version() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=1, description="v1"))
    registry.register(build_template(version=2, description="v2"))

    assert registry.get("company_research", version=1).description == "v1"
    assert registry.get("company_research", version=2).description == "v2"


def test_get_unknown_version_of_known_template_raises() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=1))

    with pytest.raises(TemplateNotFoundError):
        registry.get("company_research", version=99)


# --- Unknown template -----------------------------------------------------------


def test_get_unknown_template_id_raises() -> None:
    registry = PromptRegistry()
    with pytest.raises(TemplateNotFoundError):
        registry.get("does-not-exist")


def test_list_versions_unknown_template_raises() -> None:
    registry = PromptRegistry()
    with pytest.raises(TemplateNotFoundError):
        registry.list_versions("does-not-exist")


# --- Listing -----------------------------------------------------------


def test_list_versions_returns_sorted_versions() -> None:
    registry = PromptRegistry()
    registry.register(build_template(version=2))
    registry.register(build_template(version=1))
    registry.register(build_template(version=3))

    assert registry.list_versions("company_research") == (1, 2, 3)


def test_list_templates_returns_latest_version_metadata_sorted_by_id() -> None:
    registry = PromptRegistry()
    registry.register(build_template(template_id="zeta", version=1))
    registry.register(build_template(template_id="alpha", version=1))
    registry.register(build_template(template_id="alpha", version=2, description="alpha v2"))

    listing = registry.list_templates()

    assert [metadata.template_id for metadata in listing] == ["alpha", "zeta"]
    assert listing[0].version == 2
    assert listing[0].description == "alpha v2"


def test_list_templates_empty_registry() -> None:
    registry = PromptRegistry()
    assert registry.list_templates() == ()
