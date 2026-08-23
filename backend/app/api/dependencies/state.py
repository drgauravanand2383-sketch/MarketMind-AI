"""`resolve_app_state` — the one shared implementation behind every
`get_*_service`/`get_*_agent`/`get_*_repository` FastAPI dependency
provider across this codebase's API layer.

Deliberately lives directly under `app.api` (a sibling of `app.api.v1`,
`app.api.ws`, `app.api.intelligence` — not nested inside any of them):
`app/api/v1/__init__.py` eagerly imports the entire `/api/v1` router tree
(`from app.api.v1.router import router`), so any module reached from that
tree that imported this helper from `app.api.v1.dependencies.state`
instead would trigger that same import chain merely by importing a
"dependencies" submodule — a real circular import
(`app.api.intelligence.dependencies` -> `app.api.v1.dependencies.state`
-> `app.api.v1.__init__` -> the full v1 router tree -> back to
`app.api.intelligence.dependencies`, still initializing). `app/api
/__init__.py` is empty, so importing anything directly under `app.api`
carries no such side effect for any caller, in any direction.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

__all__ = ["resolve_app_state"]


def resolve_app_state[T](request: Request, name: str, expected_type: type[T], *, label: str) -> T:
    """Return `request.app.state.<name>`, or raise 503 if unset/None.

    `expected_type` exists only so each call site's own `T` is inferred
    from a real argument (`getattr` itself is untyped `Any`, so `T` has
    nothing else to bind against) — never `isinstance`-checked at runtime;
    an incorrectly-typed `app.state` attribute is a `app.bootstrap` bug,
    not something this dependency layer silently coerces or hides. The
    single `type: ignore` below is deliberately the *only* one for this
    entire "Any from getattr" shape in this codebase — every one of its
    ~19 previous call sites independently carried its own before this
    helper existed. `label` is the exact, independently-worded text each
    call site's 503 message already used (sometimes the bare class name,
    sometimes a friendlier phrase like "Knowledge Repository") —
    preserved verbatim, not derived from `expected_type.__name__`, so no
    caller's error message changed. (`typing.cast` cannot be used here
    instead: mypy requires its first argument to be a literal type
    expression, not an arbitrary `type[T]`-typed variable.)
    """
    component = getattr(request.app.state, name, None)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{label} is not configured on this application instance.",
        )
    return component  # type: ignore[no-any-return]
