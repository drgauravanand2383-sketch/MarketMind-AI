"""Reusable, pure, dependency-free authorization policies — evaluate an
`AuthenticatedPrincipal` against a rule with no I/O and no HTTP-framework
dependency, so every policy is just as usable outside HTTP as within it."""

from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.policies.policy import (
    Policy,
    RequireAllPermissions,
    RequireAnyRole,
    RequireAuthenticated,
    RequirePermission,
    RequireRole,
)

__all__ = [
    "Policy",
    "RequireAuthenticated",
    "RequireRole",
    "RequireAnyRole",
    "RequirePermission",
    "RequireAllPermissions",
    "PolicyEvaluator",
]
