"""Authentication middleware: resolves a bearer token and attaches the
authenticated principal to `request.state.principal`. Never authorizes —
see `AuthenticationMiddleware`'s own docstring."""

from app.auth.middleware.authentication import BEARER_PREFIX, AuthenticationMiddleware

__all__ = ["AuthenticationMiddleware", "BEARER_PREFIX"]
