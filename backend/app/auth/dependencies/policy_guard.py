"""`require_policy`: the one bridge between pure, HTTP-independent
`Policy` objects (`app.auth.policies`) and an HTTP-enforceable FastAPI
dependency. This is the only module in the whole Authentication &
Authorization Framework that turns a policy failure into an HTTP status
code — every policy itself stays framework-independent (see
`app.auth.policies`'s own docstring).

Usage:

    @router.get("/admin/x", dependencies=[Depends(require_policy(RequireRole("ADMIN")))])
    async def admin_only() -> ...: ...

`bearer_scheme` (Sprint 58): a `Security(bearer_scheme)` sub-dependency is
declared purely so FastAPI populates OpenAPI's `security`/
`securitySchemes` — giving Swagger UI its Authorize button and marking
every `require_policy`-protected endpoint as requiring Bearer auth. It
does not participate in enforcement at all: `auto_error=False` means a
missing/malformed `Authorization` header never raises here (HTTPBearer's
default `auto_error=True` would otherwise raise 403 for a missing header,
before the real 401 check below ever runs — breaking the existing
"no token -> 401" contract). Actual token verification is still done
exclusively by `AuthenticationMiddleware` (populates `request.state
.principal`) and `PolicyEvaluator` — this class is never asked for
credentials, only for its OpenAPI metadata. No authentication logic is
duplicated.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.dependencies.providers import get_current_principal, get_policy_evaluator
from app.auth.models.authentication import AuthenticatedPrincipal
from app.auth.policies.evaluator import PolicyEvaluator
from app.auth.policies.policy import Policy

__all__ = ["require_policy", "bearer_scheme"]

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="JWT access token issued by `POST /auth/login` (or equivalent). "
    "Supply as `Authorization: Bearer <token>`.",
    auto_error=False,
)


def require_policy(policy: Policy) -> Callable[..., AuthenticatedPrincipal]:
    """Return a FastAPI dependency that raises 401 (no authenticated
    principal at all) or 403 (authenticated, but `policy` denies) — and
    otherwise returns the principal, so a protected handler can also
    receive it via the same `Depends(...)` call."""

    def _dependency(
        _credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
        principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
        evaluator: PolicyEvaluator = Depends(get_policy_evaluator),
    ) -> AuthenticatedPrincipal:
        if principal is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
        if not evaluator.evaluate(policy, principal):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access denied: {policy.name}.")
        return principal

    return _dependency
