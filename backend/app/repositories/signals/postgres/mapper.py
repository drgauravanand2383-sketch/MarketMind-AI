"""Translates between SignalDefinition and the PostgreSQL ORM model.
Purely structural mapping in both directions — no business logic.
"""

from __future__ import annotations

from app.repositories.signals.postgres.models import SignalDefinitionModel
from app.signals.models import SignalCondition, SignalConditionGroup, SignalDefinition

__all__ = ["definition_to_model", "model_to_definition"]


def definition_to_model(definition: SignalDefinition) -> SignalDefinitionModel:
    """Map a `SignalDefinition` into a `SignalDefinitionModel` ready to persist."""
    return SignalDefinitionModel(
        id=definition.id,
        name=definition.name,
        description=definition.description,
        category=definition.category.value,
        enabled=definition.enabled,
        priority=definition.priority.value,
        conditions=[c.model_dump(mode="json") for c in definition.conditions],
        groups=[g.model_dump(mode="json") for g in definition.groups],
        created_at=definition.created_at,
        updated_at=definition.updated_at,
    )


def model_to_definition(model: SignalDefinitionModel) -> SignalDefinition:
    """Map a `SignalDefinitionModel` row into a `SignalDefinition`."""
    return SignalDefinition(
        id=model.id,
        name=model.name,
        description=model.description,
        category=model.category,
        enabled=model.enabled,
        priority=model.priority,
        conditions=tuple(SignalCondition.model_validate(c) for c in model.conditions),
        groups=tuple(SignalConditionGroup.model_validate(g) for g in model.groups),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
