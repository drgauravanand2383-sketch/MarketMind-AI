"""Exception hierarchy for the Authentication & Authorization Framework.

Self-contained model constraints (blank id/username, malformed email
shape) are enforced by `app.auth.models` itself and raise a plain
`pydantic.ValidationError`. This hierarchy covers everything the
application layer (`app.auth.services`) and security layer
(`app.auth.security`) enforce: rules that depend on existing repository
state (not found, duplicate), credential/token verification outcomes, and
authorization decisions.
"""

from __future__ import annotations

__all__ = [
    "AuthError",
    "UserNotFoundError",
    "DuplicateUsernameError",
    "DuplicateEmailError",
    "WeakPasswordError",
    "InvalidCredentialsError",
    "UserNotActiveError",
    "RoleNotFoundError",
    "DuplicateRoleNameError",
    "TokenError",
    "TokenMalformedError",
    "TokenInvalidError",
    "TokenExpiredError",
    "TokenRevokedError",
    "TokenTypeMismatchError",
    "AuthorizationDeniedError",
]


class AuthError(Exception):
    """Base class for every error raised by the Authentication & Authorization Framework."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class UserNotFoundError(AuthError):
    """Raised when no user exists for the given id/username/email."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No user found for {identifier!r}.")


class DuplicateUsernameError(AuthError):
    """Raised when registering a user with a username already in use."""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"Username {username!r} is already in use.")


class DuplicateEmailError(AuthError):
    """Raised when registering a user with an email already in use."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email {email!r} is already in use.")


class WeakPasswordError(AuthError):
    """Raised when a password fails the configured strength policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Password does not meet strength requirements: {reason}")


class InvalidCredentialsError(AuthError):
    """Raised when a username/password combination does not authenticate.
    Deliberately generic — never reveals whether the username or the
    password was the specific failure, to avoid user enumeration."""

    def __init__(self) -> None:
        super().__init__("Invalid username or password.")


class UserNotActiveError(AuthError):
    """Raised when a user exists but is not `UserStatus.ACTIVE`
    (DISABLED, LOCKED, or PENDING)."""

    def __init__(self, user_id: str, status: str) -> None:
        self.user_id = user_id
        self.status = status
        super().__init__(f"User {user_id!r} is not active (status={status}).")


class RoleNotFoundError(AuthError):
    """Raised when no role exists for the given id/name."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No role found for {identifier!r}.")


class DuplicateRoleNameError(AuthError):
    """Raised when creating a role with a name already in use."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A role named {name!r} already exists.")


class TokenError(AuthError):
    """Base class for every token validation failure. Never includes the
    raw token or the signing secret in its message."""


class TokenMalformedError(TokenError):
    """Raised when a token is not well-formed (wrong segment count, invalid
    base64url, invalid JSON, unexpected algorithm)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Token is malformed: {reason}")


class TokenInvalidError(TokenError):
    """Raised when a token's signature does not verify."""

    def __init__(self) -> None:
        super().__init__("Token signature is invalid.")


class TokenExpiredError(TokenError):
    """Raised when a token's `exp` claim has passed, beyond the configured
    clock-skew tolerance."""

    def __init__(self) -> None:
        super().__init__("Token has expired.")


class TokenRevokedError(TokenError):
    """Raised when a token's `jti` has been explicitly revoked."""

    def __init__(self) -> None:
        super().__init__("Token has been revoked.")


class TokenTypeMismatchError(TokenError):
    """Raised when a token's `typ` claim does not match what the caller
    expected (e.g. a refresh token presented where an access token is required)."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"Expected a {expected!r} token, got {actual!r}.")


class AuthorizationDeniedError(AuthError):
    """Raised by `PolicyEvaluator.check()` when a policy evaluates to `False`."""

    def __init__(self, policy_name: str) -> None:
        self.policy_name = policy_name
        super().__init__(f"Access denied: policy {policy_name!r} was not satisfied.")
