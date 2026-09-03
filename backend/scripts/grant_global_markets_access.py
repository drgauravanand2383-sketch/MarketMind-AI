"""Operational script — grant `global_markets:read` to the users who
should see the Global Market Intelligence feature (dashboard card, the
`/global-markets` page, the `/api/v1/global-markets/*` endpoints, and the
`GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED` WebSocket event).

There is no admin UI for role/permission management (see
`docs/release/ADMINISTRATOR_GUIDE.md`) and `BaseAuthRepository` has no
`update_role` — so a grant is a deliberate ops action. This script does
it the additive, reversible way, using only the repository methods that
already exist:

  1. `create_role` a single dedicated role, `GLOBAL_MARKETS_READ`
     (id `role-global-markets-read`), holding exactly the one permission
     `global_markets:read` — created once, idempotently.
  2. `assign_role` that role to each named user (idempotent — assigning
     an already-held role is a no-op).

No existing role is mutated; no permission is removed; authorization is
never weakened. To revoke, `revoke_role` the same role from a user.

Usage (matches the other `scripts/*.py`):

    docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
        exec backend python scripts/grant_global_markets_access.py

    # or, to target a specific set of usernames:
    ... python scripts/grant_global_markets_access.py pilot_investor alice

Prints a JSON summary and exits 0 on success, 1 if the auth repository is
unavailable. Never prints a password, token, or hash.
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi import FastAPI

from app.auth.models.role import Role
from app.bootstrap import bootstrap_application_state, shutdown_application_state

_ROLE_ID = "role-global-markets-read"
_ROLE_NAME = "GLOBAL_MARKETS_READ"
_ROLE_DESCRIPTION = "Read access to Global Market Intelligence (dashboard card, /global-markets, API, WS)."
_PERMISSION = "global_markets:read"

# The users who should have Global Market Intelligence access by default.
# `pilot_investor` is the end-user investor persona; the two acceptance
# users exercise the full UI workflow. Override by passing usernames as
# CLI args.
_DEFAULT_USERNAMES = ("pilot_investor", "acceptance_test_user", "m14_acceptance_user")


async def _run(usernames: tuple[str, ...]) -> int:
    app = FastAPI()
    await bootstrap_application_state(app)
    try:
        repository = getattr(app.state, "auth_repository", None)
        authorization = getattr(app.state, "authorization_service", None)
        if repository is None or authorization is None:
            print(json.dumps({"status": "unavailable", "reason": "auth repository not configured"}))
            return 1

        existing = await repository.get_role(_ROLE_ID)
        if existing is None:
            await repository.create_role(
                Role(
                    id=_ROLE_ID,
                    name=_ROLE_NAME,
                    description=_ROLE_DESCRIPTION,
                    permissions=(_PERMISSION,),
                )
            )
            role_action = "created"
        else:
            role_action = "already-present"

        results: list[dict[str, object]] = []
        for username in usernames:
            user = await repository.get_user_by_username(username)
            if user is None:
                results.append({"username": username, "outcome": "user-not-found"})
                continue
            already = _ROLE_ID in user.roles
            if not already:
                await repository.assign_role(user.id, _ROLE_ID)
            refreshed = await repository.get_user(user.id)
            effective = await authorization.resolve_effective_permissions(refreshed) if refreshed else frozenset()
            results.append(
                {
                    "username": username,
                    "outcome": "already-assigned" if already else "assigned",
                    "has_global_markets_read": _PERMISSION in effective,
                }
            )

        print(json.dumps({"status": "ok", "role": role_action, "role_id": _ROLE_ID, "users": results}, indent=2))
        return 0
    finally:
        await shutdown_application_state(app)


def main() -> None:
    args = tuple(sys.argv[1:])
    usernames = args or _DEFAULT_USERNAMES
    sys.exit(asyncio.run(_run(usernames)))


if __name__ == "__main__":
    main()
