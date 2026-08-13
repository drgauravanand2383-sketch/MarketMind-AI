"""Auth API (`/api/v1/auth`): exposes `app.auth.services.authentication
.AuthenticationService` — login/refresh/logout — over REST for the first
time. Every endpoint delegates directly to an existing method; no
authentication logic is duplicated."""

from app.api.v1.auth.router import router

__all__ = ["router"]
