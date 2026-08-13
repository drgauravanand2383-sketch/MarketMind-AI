"""Translates between ScreeningProfile and the PostgreSQL ORM model.
Purely structural mapping in both directions — no business logic.
"""

from __future__ import annotations

from app.repositories.screening.postgres.models import ScreeningProfileModel
from app.screening.models import LogicalGroup, ScreenFilter, ScreeningProfile

__all__ = ["profile_to_model", "model_to_profile"]


def profile_to_model(profile: ScreeningProfile) -> ScreeningProfileModel:
    """Map a `ScreeningProfile` into a `ScreeningProfileModel` ready to persist."""
    return ScreeningProfileModel(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        is_default=profile.is_default,
        filters=[f.model_dump(mode="json") for f in profile.filters],
        groups=[g.model_dump(mode="json") for g in profile.groups],
    )


def model_to_profile(model: ScreeningProfileModel) -> ScreeningProfile:
    """Map a `ScreeningProfileModel` row into a `ScreeningProfile`."""
    return ScreeningProfile(
        id=model.id,
        name=model.name,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        is_default=model.is_default,
        filters=tuple(ScreenFilter.model_validate(f) for f in model.filters),
        groups=tuple(LogicalGroup.model_validate(g) for g in model.groups),
    )
