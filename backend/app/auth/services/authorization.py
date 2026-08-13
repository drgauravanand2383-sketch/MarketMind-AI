"""AuthorizationService: resolves a `User`'s *effective* roles and
permissions — RBAC with role hierarchy and permission inheritance.

A user's effective permission set is the union of their own directly-
granted `permissions` and every permission granted by each role in
`roles`, walked recursively up that role's `parent_id` chain (a role
inherits everything its parent grants, and so on). Cycle-safe: a
`parent_id` chain that loops back on itself (a deployment/data error, not
something this framework prevents at write time) stops resolving instead
of recursing forever, once a role id is revisited.

This service performs the one piece of *resolution* (I/O against
`BaseAuthRepository`, walking hierarchy) in the whole authorization
story. Everything downstream of it — every `app.auth.policies` policy —
checks an already-resolved `AuthenticatedPrincipal.roles`/`.permissions`
and needs no repository access, no I/O, and no knowledge of hierarchy at
all (see `app.auth.policies`'s own module docstring for why that split
exists).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.auth.models.user import User

if TYPE_CHECKING:
    from app.auth.repositories.repository import BaseAuthRepository

__all__ = ["AuthorizationService"]


class AuthorizationService:
    def __init__(self, repository: BaseAuthRepository) -> None:
        self._repository = repository

    async def resolve_effective_permissions(self, user: User) -> frozenset[str]:
        """The union of `user.permissions` and every permission granted
        by `user.roles`, recursively through role hierarchy."""
        permissions: set[str] = set(user.permissions)
        for role_id in user.roles:
            permissions |= await self._resolve_role_permissions(role_id, seen=set())
        return frozenset(permissions)

    async def resolve_role_names(self, user: User) -> tuple[str, ...]:
        """`user.roles` (ids), resolved to their `Role.name` values — a
        role id with no matching stored role is silently skipped (it
        cannot contribute a name)."""
        names: list[str] = []
        for role_id in user.roles:
            role = await self._repository.get_role(role_id)
            if role is not None:
                names.append(role.name)
        return tuple(names)

    async def has_permission(self, user: User, permission: str) -> bool:
        return permission in await self.resolve_effective_permissions(user)

    async def has_role(self, user: User, role_name: str) -> bool:
        return role_name in await self.resolve_role_names(user)

    async def _resolve_role_permissions(self, role_id: str, *, seen: set[str]) -> frozenset[str]:
        if role_id in seen:
            return frozenset()
        seen.add(role_id)
        role = await self._repository.get_role(role_id)
        if role is None:
            return frozenset()
        permissions = set(role.permissions)
        if role.parent_id is not None:
            permissions |= await self._resolve_role_permissions(role.parent_id, seen=seen)
        return frozenset(permissions)
