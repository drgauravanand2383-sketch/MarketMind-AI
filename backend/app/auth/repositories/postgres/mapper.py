"""Translates between User/Role and their PostgreSQL ORM models. Purely
structural mapping in both directions — no business logic, aside from the
same naive-datetime-from-SQLite normalization `app.repositories.alerts
.postgres.mapper` established (Sprint 48); repeated here since these are
independent modules with no shared base to place it in. `password_hash`
never appears on the `User` domain model — the mapper reads/writes it as
a separate concern (`user_to_model` takes it as an explicit parameter;
`model_to_user` simply never puts it on the returned `User`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.auth.models.role import Role
from app.auth.models.user import User, UserStatus
from app.auth.repositories.postgres.models import RoleModel, UserModel

__all__ = ["user_to_model", "model_to_user", "role_to_model", "model_to_role"]


def _ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def user_to_model(user: User, password_hash: str) -> UserModel:
    """Map a `User` (plus its separately-tracked password hash) into a `UserModel` ready to persist."""
    return UserModel(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status.value,
        password_hash=password_hash,
        role_ids=list(user.roles),
        direct_permissions=list(user.permissions),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def model_to_user(model: UserModel) -> User:
    """Map a `UserModel` row into a `User` — never includes `password_hash`."""
    return User(
        id=model.id,
        username=model.username,
        email=model.email,
        display_name=model.display_name,
        status=UserStatus(model.status),
        roles=tuple(model.role_ids),
        permissions=tuple(model.direct_permissions),
        created_at=_ensure_aware(model.created_at),
        updated_at=_ensure_aware(model.updated_at),
    )


def role_to_model(role: Role) -> RoleModel:
    return RoleModel(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=list(role.permissions),
        parent_id=role.parent_id,
    )


def model_to_role(model: RoleModel) -> Role:
    return Role(
        id=model.id,
        name=model.name,
        description=model.description,
        permissions=tuple(model.permissions),
        parent_id=model.parent_id,
    )
