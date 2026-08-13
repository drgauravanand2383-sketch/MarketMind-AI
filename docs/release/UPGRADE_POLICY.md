# MarketMind AI — Upgrade Policy

RC1 is the first tagged release — there is no prior version to upgrade
*from* yet. This document establishes the policy future releases follow.

## Versioning scheme

Semantic-versioning-flavored: `MAJOR.MINOR.PATCH`.

- **MAJOR** — a breaking `/api/v1` contract change (requires a new
  `/api/v2` per `docs/release/API_VERSIONING_POLICY.md` — `/api/v1`
  itself never breaks in place), or a breaking change to `/ws`'s message
  protocol.
- **MINOR** — a new endpoint, a new optional field, a new `/ws` event
  type, a new configuration option — anything additive and backward
  compatible per `docs/release/API_VERSIONING_POLICY.md`.
- **PATCH** — a bug fix that does not change any documented contract
  behavior (e.g. a genuine production defect fixed under this sprint's
  own "absolutely required" exception), a documentation correction, a
  dependency update with no behavior change, a test-only change.

## Database migrations

Every release that changes the schema ships a new Alembic revision —
never a modification of an already-released revision (`0001_baseline_schema`
and everything after it are permanent once shipped). Upgrading always
means `alembic upgrade head`; downgrading (`alembic downgrade <revision>`)
is supported for every revision but is a destructive operation on any
data added since — treat it as a last resort, not routine rollback.

## Configuration changes

A new required setting (no default) is a **MAJOR** change — it breaks
any deployment that doesn't already have it set. A new *optional*
setting with a sensible default is **MINOR**. Removing a setting
entirely (even one that was already optional) is **MAJOR** if anything
still reads it — check `ConfigurationValidationService` for whether
removing a field would silently break a still-referencing `build_*`
function first.

## Deprecation before removal

Nothing in `/api/v1` is ever removed without first existing, working,
and documented as deprecated for at least one full MINOR release cycle
— see `docs/release/API_VERSIONING_POLICY.md`'s deprecation-window
section. The same applies to configuration settings: a removed setting
is announced as deprecated (with a warning if still set) at least one
release before actual removal.

## Dependency upgrades

Python/library version bumps follow whatever compatibility guarantee
the underlying dependency itself provides — this project pins
`requires-python = ">=3.13"` and does not otherwise pin exact dependency
versions beyond `pyproject.toml`'s own ranges. A dependency major-version
bump that changes this application's own behavior is treated as at least
**MINOR** (document what changed) even if no line of application code
changed.

## What every release must include

Per `docs/release/RELEASE_CHECKLIST.md`: updated release notes, a full
green test run (zero regressions), OpenAPI validated, and — for any
release touching `/api/v1` or `/ws` — an updated `docs/release/API_CONTRACT_V1.md`
(or `docs/architecture/WEBSOCKET_FRAMEWORK.md`) reflecting exactly what
changed and why it was or wasn't a breaking change under this policy.
