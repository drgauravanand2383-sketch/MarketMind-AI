"""Reusable authorization policies.

Every policy here is a pure, synchronous, dependency-free check against
an already-resolved `AuthenticatedPrincipal` — no repository access, no
I/O, no `AuthorizationService`, and no HTTP-framework import anywhere in
this module. This is exactly what "Policies must remain reusable outside
HTTP" means: a policy is just as usable from a CLI command, a background
job, or a unit test as from an HTTP request — it needs nothing but a
principal (or `None`, for an unauthenticated caller) to evaluate.

This works because `AuthenticatedPrincipal.roles`/`.permissions` already
hold the *effective*, hierarchy-resolved sets —
`app.auth.services.authorization.AuthorizationService` did that
resolution once, at token-issuance time (see
`app.auth.providers.jwt`'s own docstring); a policy only ever compares
against what's already there, in-memory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.auth.models.authentication import AuthenticatedPrincipal

__all__ = [
    "Policy",
    "RequireAuthenticated",
    "RequireRole",
    "RequireAnyRole",
    "RequirePermission",
    "RequireAllPermissions",
]


class Policy(ABC):
    """Abstract base class every authorization policy must inherit."""

    @abstractmethod
    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        """Whether `principal` (`None` for an unauthenticated caller)
        satisfies this policy."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        return type(self).__name__


class RequireAuthenticated(Policy):
    """Satisfied by any authenticated principal — the base building
    block every other policy in this module implicitly requires too
    (all of them return `False` for `principal=None`)."""

    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        return principal is not None


class RequireRole(Policy):
    """Satisfied when the principal holds exactly the named role."""

    def __init__(self, role: str) -> None:
        self._role = role

    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        return principal is not None and self._role in principal.roles

    @property
    def name(self) -> str:
        return f"RequireRole({self._role!r})"


class RequireAnyRole(Policy):
    """Satisfied when the principal holds at least one of the named roles."""

    def __init__(self, *roles: str) -> None:
        self._roles = frozenset(roles)

    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        return principal is not None and bool(self._roles & set(principal.roles))

    @property
    def name(self) -> str:
        return f"RequireAnyRole({sorted(self._roles)!r})"


class RequirePermission(Policy):
    """Satisfied when the principal holds the named effective permission."""

    def __init__(self, permission: str) -> None:
        self._permission = permission

    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        return principal is not None and self._permission in principal.permissions

    @property
    def name(self) -> str:
        return f"RequirePermission({self._permission!r})"


class RequireAllPermissions(Policy):
    """Satisfied when the principal holds every one of the named effective permissions."""

    def __init__(self, *permissions: str) -> None:
        self._permissions = frozenset(permissions)

    def evaluate(self, principal: AuthenticatedPrincipal | None) -> bool:
        return principal is not None and self._permissions.issubset(principal.permissions)

    @property
    def name(self) -> str:
        return f"RequireAllPermissions({sorted(self._permissions)!r})"
