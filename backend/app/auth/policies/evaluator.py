"""PolicyEvaluator: the small orchestrator that runs a `Policy` against a
principal and turns a failed evaluation into `AuthorizationDeniedError`.
Contains no policy logic of its own — every actual rule lives in the
`Policy` subclasses themselves (`app.auth.policies.policy`)."""

from __future__ import annotations

from app.auth.exceptions import AuthorizationDeniedError
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies.policy import Policy

__all__ = ["PolicyEvaluator"]


class PolicyEvaluator:
    def evaluate(self, policy: Policy, principal: AuthenticatedPrincipal | None) -> bool:
        return policy.evaluate(principal)

    def check(self, policy: Policy, principal: AuthenticatedPrincipal | None) -> None:
        """Raises `AuthorizationDeniedError` if `policy` is not satisfied."""
        if not self.evaluate(policy, principal):
            raise AuthorizationDeniedError(policy.name)
