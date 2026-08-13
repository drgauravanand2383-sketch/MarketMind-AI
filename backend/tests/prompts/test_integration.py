"""Integration tests: PromptRegistry + PromptRenderer working together.

Covers version selection through `render(template_id=..., variables=...)`
and confirms the "Future Compatibility" call shape works without the
caller knowing how templates are stored.
"""

from __future__ import annotations

import pytest

from app.prompts.exceptions import TemplateNotFoundError
from app.prompts.registry import PromptRegistry
from app.prompts.renderer import PromptRenderer
from tests.prompts.conftest import build_template


def _wired() -> tuple[PromptRegistry, PromptRenderer]:
    registry = PromptRegistry()
    renderer = PromptRenderer(registry)
    return registry, renderer


# --- registry + renderer -----------------------------------------------------------


def test_render_by_template_id_resolves_through_the_registry() -> None:
    registry, renderer = _wired()
    registry.register(build_template())

    result = renderer.render(
        template_id="company_research", variables={"company_name": "Acme", "sector": "Tech"}
    )

    assert result.user_prompt == "Research the company Acme in the Tech sector."


def test_render_unknown_template_id_raises() -> None:
    _registry, renderer = _wired()

    with pytest.raises(TemplateNotFoundError):
        renderer.render(template_id="does-not-exist", variables={})


def test_a_template_registered_after_renderer_construction_is_still_reachable() -> None:
    """The renderer holds a reference to the registry, not a snapshot —
    templates registered later are immediately renderable."""
    registry, renderer = _wired()

    registry.register(build_template())

    result = renderer.render(
        template_id="company_research", variables={"company_name": "Acme", "sector": "Tech"}
    )
    assert result.template_id == "company_research"


# --- Version selection -----------------------------------------------------------


def test_render_selects_latest_version_by_default() -> None:
    registry, renderer = _wired()
    registry.register(build_template(version=1, user_prompt="v1: {company_name}"))
    registry.register(build_template(version=2, user_prompt="v2: {company_name}"))

    result = renderer.render(template_id="company_research", variables={"company_name": "Acme"})

    assert result.version == 2
    assert result.user_prompt == "v2: Acme"


def test_render_selects_a_specific_version_when_given() -> None:
    registry, renderer = _wired()
    registry.register(build_template(version=1, user_prompt="v1: {company_name}"))
    registry.register(build_template(version=2, user_prompt="v2: {company_name}"))

    result = renderer.render(
        template_id="company_research", variables={"company_name": "Acme"}, version=1
    )

    assert result.version == 1
    assert result.user_prompt == "v1: Acme"


def test_render_unknown_version_raises() -> None:
    registry, renderer = _wired()
    registry.register(build_template(version=1))

    with pytest.raises(TemplateNotFoundError):
        renderer.render(template_id="company_research", variables={}, version=99)


# --- Rendered output -----------------------------------------------------------


def test_render_via_template_id_matches_manual_render_template_call() -> None:
    registry, renderer = _wired()
    template = build_template()
    registry.register(template)
    variables = {"company_name": "Acme", "sector": "Tech"}

    via_id = renderer.render(template_id="company_research", variables=variables)
    via_template = renderer.render_template(template, variables)

    assert via_id == via_template


def test_agents_can_render_without_knowing_how_templates_are_stored() -> None:
    """Mirrors the sprint's "Future Compatibility" call shape exactly."""
    registry, renderer = _wired()
    registry.register(build_template())

    result = renderer.render(
        template_id="company_research", variables={"company_name": "Acme", "sector": "Tech"}
    )

    assert result.system_prompt
    assert result.user_prompt
    assert result.template_id == "company_research"
