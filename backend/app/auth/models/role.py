"""Role domain model and the framework's four built-in role names.

Design note — additive `Role.parent_id`: the sprint's own "Role
hierarchy" and "Permission inheritance" requirements are unimplementable
against the literal `Role` field list (`id`, `name`, `description`,
`permissions`) alone — nothing on it expresses which role a given role
inherits from. `parent_id` (optional; `None` means a root role) adds
exactly that, flagged per this codebase's established precedent for a
structurally-necessary field the literal spec omitted. A role's
*effective* permissions are its own `permissions` plus its parent's
effective permissions, recursively — resolved by
`app.auth.services.authorization.AuthorizationService`, never
recalculated ad hoc elsewhere.

`BuiltinRole` names the four roles this sprint's own "Built-in roles"
section lists. It is a closed enum of *names* only — no `Role` instance,
permission set, or hierarchy is seeded by this framework itself (no
fixed permission catalog exists to assign); a deployment constructs and
persists its own `Role` rows (e.g. `Role(id=..., name=BuiltinRole.ADMIN,
...)`) via `BaseAuthRepository.create_role()`, choosing its own
permissions and parent chain.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["BuiltinRole", "Role"]


class BuiltinRole(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"
    API_CLIENT = "API_CLIENT"


class Role(BaseModel):
    """A named, reusable set of permissions, optionally inheriting from
    one parent role (see module docstring)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    permissions: tuple[str, ...] = Field(default_factory=tuple)
    parent_id: str | None = None
