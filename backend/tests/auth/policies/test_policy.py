"""Tests for the reusable authorization policies. Pure, no I/O — every
test here constructs an `AuthenticatedPrincipal` directly, no repository
or provider involved, demonstrating "reusable outside HTTP" directly."""

from __future__ import annotations

from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies.policy import (
    RequireAllPermissions,
    RequireAnyRole,
    RequireAuthenticated,
    RequirePermission,
    RequireRole,
)


def _principal(roles: tuple[str, ...] = (), permissions: tuple[str, ...] = ()) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id="u1", username="alice", roles=roles, permissions=permissions, token_id="t1")


# --- RequireAuthenticated -----------------------------------------------------------


def test_require_authenticated_satisfied_by_any_principal() -> None:
    assert RequireAuthenticated().evaluate(_principal()) is True


def test_require_authenticated_denied_for_none() -> None:
    assert RequireAuthenticated().evaluate(None) is False


# --- RequireRole -----------------------------------------------------------


def test_require_role_satisfied_when_role_present() -> None:
    assert RequireRole("ADMIN").evaluate(_principal(roles=("ADMIN",))) is True


def test_require_role_denied_when_role_absent() -> None:
    assert RequireRole("ADMIN").evaluate(_principal(roles=("VIEWER",))) is False


def test_require_role_denied_for_none() -> None:
    assert RequireRole("ADMIN").evaluate(None) is False


def test_require_role_name_includes_the_role() -> None:
    assert "ADMIN" in RequireRole("ADMIN").name


# --- RequireAnyRole -----------------------------------------------------------


def test_require_any_role_satisfied_with_one_matching_role() -> None:
    assert RequireAnyRole("ADMIN", "ANALYST").evaluate(_principal(roles=("ANALYST",))) is True


def test_require_any_role_denied_with_no_matching_role() -> None:
    assert RequireAnyRole("ADMIN", "ANALYST").evaluate(_principal(roles=("VIEWER",))) is False


def test_require_any_role_denied_for_none() -> None:
    assert RequireAnyRole("ADMIN").evaluate(None) is False


# --- RequirePermission -----------------------------------------------------------


def test_require_permission_satisfied_when_permission_present() -> None:
    assert RequirePermission("read").evaluate(_principal(permissions=("read", "write"))) is True


def test_require_permission_denied_when_permission_absent() -> None:
    assert RequirePermission("delete").evaluate(_principal(permissions=("read",))) is False


def test_require_permission_denied_for_none() -> None:
    assert RequirePermission("read").evaluate(None) is False


# --- RequireAllPermissions -----------------------------------------------------------


def test_require_all_permissions_satisfied_when_all_present() -> None:
    policy = RequireAllPermissions("read", "write")
    assert policy.evaluate(_principal(permissions=("read", "write", "delete"))) is True


def test_require_all_permissions_denied_when_one_missing() -> None:
    policy = RequireAllPermissions("read", "write")
    assert policy.evaluate(_principal(permissions=("read",))) is False


def test_require_all_permissions_denied_for_none() -> None:
    assert RequireAllPermissions("read").evaluate(None) is False


def test_require_all_permissions_satisfied_with_empty_requirement_set() -> None:
    assert RequireAllPermissions().evaluate(_principal()) is True
