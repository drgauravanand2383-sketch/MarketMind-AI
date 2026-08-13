"""FastAPI dependency providers for the Authentication & Authorization
Framework. `app/api/` consumes these via dependency injection — this
package never imports from `app.api`."""

from app.auth.dependencies.policy_guard import require_policy
from app.auth.dependencies.providers import (
    get_authentication_service,
    get_authorization_service,
    get_current_principal,
    get_policy_evaluator,
)

__all__ = [
    "get_authentication_service",
    "get_authorization_service",
    "get_policy_evaluator",
    "get_current_principal",
    "require_policy",
]
