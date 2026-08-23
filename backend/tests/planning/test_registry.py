"""Tests for PlanRegistry."""

from __future__ import annotations

import contextlib

import pytest

from app.planning.exceptions import PlanTemplateAlreadyRegisteredError, UnknownObjectiveError
from app.planning.models import PlanTemplate
from app.planning.registry import PlanRegistry


def _template(objective: str, template_id: str | None = None) -> PlanTemplate:
    return PlanTemplate(template_id=template_id or f"tmpl-{objective}", objective=objective, steps=())


def test_register_then_get_returns_the_same_template() -> None:
    registry = PlanRegistry()
    template = _template("company research")
    registry.register(template)

    assert registry.get("company research") is template


def test_list_objectives_returns_sorted_objectives() -> None:
    registry = PlanRegistry()
    registry.register(_template("morning brief"))
    registry.register(_template("company research"))

    assert registry.list_objectives() == ("company research", "morning brief")


def test_list_objectives_empty_when_nothing_registered() -> None:
    registry = PlanRegistry()
    assert registry.list_objectives() == ()


def test_duplicate_registration_raises() -> None:
    registry = PlanRegistry()
    registry.register(_template("company research"))

    with pytest.raises(PlanTemplateAlreadyRegisteredError):
        registry.register(_template("company research", template_id="a-different-id"))


def test_duplicate_registration_does_not_replace_existing_template() -> None:
    registry = PlanRegistry()
    first = _template("company research", template_id="first")
    registry.register(first)

    with contextlib.suppress(PlanTemplateAlreadyRegisteredError):
        registry.register(_template("company research", template_id="second"))

    assert registry.get("company research") is first


def test_get_unknown_objective_raises() -> None:
    registry = PlanRegistry()
    with pytest.raises(UnknownObjectiveError):
        registry.get("does-not-exist")
