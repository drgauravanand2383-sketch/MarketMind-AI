"""Tests for AuthorizationService: effective permission resolution with
role hierarchy/inheritance, and cycle safety."""

from __future__ import annotations

from app.auth.models.user import User
from app.auth.services.authorization import AuthorizationService
from tests.auth.conftest import NOW, make_role


def _user(roles: tuple[str, ...] = (), permissions: tuple[str, ...] = ()) -> User:
    return User(
        id="u1", username="alice", email="alice@example.com", roles=roles, permissions=permissions,
        created_at=NOW, updated_at=NOW,
    )


async def test_resolve_effective_permissions_includes_direct_permissions(
    authorization_service: AuthorizationService,
) -> None:
    user = _user(permissions=("read",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"read"})


async def test_resolve_effective_permissions_includes_role_permissions(
    authorization_service: AuthorizationService, repository,
) -> None:
    await make_role(repository, "r1", "VIEWER", permissions=("read",))
    user = _user(roles=("r1",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"read"})


async def test_resolve_effective_permissions_walks_role_hierarchy(
    authorization_service: AuthorizationService, repository,
) -> None:
    await make_role(repository, "r-viewer", "VIEWER", permissions=("read",))
    await make_role(repository, "r-analyst", "ANALYST", permissions=("analyze",), parent_id="r-viewer")
    await make_role(repository, "r-admin", "ADMIN", permissions=("manage",), parent_id="r-analyst")
    user = _user(roles=("r-admin",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"manage", "analyze", "read"})


async def test_resolve_effective_permissions_combines_direct_and_role_permissions(
    authorization_service: AuthorizationService, repository,
) -> None:
    await make_role(repository, "r1", "VIEWER", permissions=("read",))
    user = _user(roles=("r1",), permissions=("special",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"read", "special"})


async def test_resolve_effective_permissions_deduplicates_across_roles(
    authorization_service: AuthorizationService, repository,
) -> None:
    await make_role(repository, "r1", "A", permissions=("shared", "one"))
    await make_role(repository, "r2", "B", permissions=("shared", "two"))
    user = _user(roles=("r1", "r2"))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"shared", "one", "two"})


async def test_resolve_effective_permissions_unknown_role_id_contributes_nothing(
    authorization_service: AuthorizationService,
) -> None:
    user = _user(roles=("does-not-exist",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset()


async def test_resolve_effective_permissions_is_cycle_safe(
    authorization_service: AuthorizationService, repository,
) -> None:
    """A `parent_id` chain that loops (a data error this framework
    doesn't prevent at write time) must not recurse forever."""
    await make_role(repository, "r1", "A", permissions=("perm-a",), parent_id="r2")
    await make_role(repository, "r2", "B", permissions=("perm-b",), parent_id="r1")  # cycle: r1 -> r2 -> r1
    user = _user(roles=("r1",))

    effective = await authorization_service.resolve_effective_permissions(user)

    assert effective == frozenset({"perm-a", "perm-b"})


async def test_resolve_role_names(authorization_service: AuthorizationService, repository) -> None:
    await make_role(repository, "r1", "ADMIN")
    await make_role(repository, "r2", "VIEWER")
    user = _user(roles=("r1", "r2"))

    names = await authorization_service.resolve_role_names(user)

    assert set(names) == {"ADMIN", "VIEWER"}


async def test_resolve_role_names_skips_unknown_role_ids(
    authorization_service: AuthorizationService, repository,
) -> None:
    await make_role(repository, "r1", "ADMIN")
    user = _user(roles=("r1", "does-not-exist"))

    names = await authorization_service.resolve_role_names(user)

    assert names == ("ADMIN",)


async def test_has_permission(authorization_service: AuthorizationService, repository) -> None:
    await make_role(repository, "r1", "VIEWER", permissions=("read",))
    user = _user(roles=("r1",))

    assert await authorization_service.has_permission(user, "read") is True
    assert await authorization_service.has_permission(user, "write") is False


async def test_has_role(authorization_service: AuthorizationService, repository) -> None:
    await make_role(repository, "r1", "ADMIN")
    user = _user(roles=("r1",))

    assert await authorization_service.has_role(user, "ADMIN") is True
    assert await authorization_service.has_role(user, "VIEWER") is False
