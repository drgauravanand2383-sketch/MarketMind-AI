"""Tests for the Role/Permission/BuiltinRole domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.auth.models.permission import Permission
from app.auth.models.role import BuiltinRole, Role


def test_role_defaults() -> None:
    role = Role(id="r1", name="ADMIN")
    assert role.description == ""
    assert role.permissions == ()
    assert role.parent_id is None


def test_role_accepts_parent_id_for_hierarchy() -> None:
    role = Role(id="r2", name="ANALYST", parent_id="r1")
    assert role.parent_id == "r1"


def test_role_rejects_blank_id() -> None:
    with pytest.raises(ValidationError):
        Role(id="", name="ADMIN")


def test_role_is_frozen() -> None:
    role = Role(id="r1", name="ADMIN")
    with pytest.raises(ValidationError):
        role.name = "VIEWER"  # type: ignore[misc]


def test_builtin_role_has_exactly_four_names() -> None:
    assert {r.value for r in BuiltinRole} == {"ADMIN", "ANALYST", "VIEWER", "API_CLIENT"}


def test_permission_defaults() -> None:
    permission = Permission(id="p1", name="read")
    assert permission.description == ""


def test_permission_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        Permission(id="p1", name="")
