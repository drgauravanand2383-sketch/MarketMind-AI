# MarketMind AI — Version 1.0.0 Release Notes

Milestone 10, Release Engineering & Production Readiness. **This is the
first full-stack release** — `docs/release/RELEASE_NOTES_RC1.md`
covered the backend/API/WebSocket layer alone; v1.0.0 adds the complete
frontend (Milestones 2-9) and everything needed to build, deploy, and
operate the whole system in production.

## What's in v1.0.0

**Backend** — unchanged since RC1 (Sprints 1-60): the full multi-agent
market intelligence engine, a frozen `/api/v1` REST surface (44 paths,
50 operations), and a real-time `/ws` WebSocket. See
`docs/release/RELEASE_NOTES_RC1.md` for the full backend history.

**Frontend** (new for v1.0.0) — a complete React/TanStack single-page
application, built across 8 domain milestones plus a production-quality
pass:

- Authentication, application shell, and routing
- Dashboard with customizable, real-time-updating cards
- Watchlists & portfolio management
- Company research and multi-criteria market screening
- Decision Center (recommendations, strategy, risk, signals, alerts)
- Historical Analysis (backtesting, explainability, performance
  attribution)
- Real-time experience — live WebSocket-driven updates, a Notification
  Center, connection diagnostics with automatic reconnection
- User settings & personalization (theme, dashboard layout, saved
  views, import/export)
- A dedicated production-quality pass: full accessibility audit and
  fixes (keyboard navigation, focus management, ARIA live regions,
  color contrast), Recharts lazy-loading, mobile responsiveness fixes,
  error-recovery UX (retry affordances, offline awareness, reactive
  session-expiry, per-card error isolation), a shared design-system
  `Button` component, and a configurable keyboard-shortcuts system

**Release engineering** (this milestone):

- Production Docker images for both the frontend (multi-stage Node
  build → nginx) and the backend (previously had none)
- `docker-compose.prod.yml` — an additive local production-testing
  stack, layered on top of the existing infra-only `docker-compose.yml`
  without changing its documented behavior
- Frontend environment validation — a missing/malformed
  `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` now fails loudly and clearly at
  load time in a production build, instead of silently falling back to
  `localhost`
- GitHub Actions CI for both halves of the app (typecheck/lint/test/
  build for the frontend; pytest/build for the backend, with ruff/mypy
  as advisory, non-blocking checks against this codebase's existing
  lint/type debt) and a tagged-release workflow producing named,
  versioned artifacts
- A full-stack security review (`docs/release/SECURITY_REVIEW_V1.md`) —
  frontend security headers now match the backend's existing baseline;
  a dependency audit found and mitigated one real finding (an
  unpatched ChromaDB advisory, mitigated by no longer publishing its
  port outside the Docker network)
- A full documentation set: Installation, Deployment (extended),
  Administrator, User, Troubleshooting, and Architecture Overview
  guides, plus this release notes document

## Fixed in this release

- `backend/pyproject.toml`'s `readme` field pointed outside the project
  directory (`../README.md`), which modern `hatchling` rejects — this
  silently broke the *already-documented* `pip install -e .` /
  `uv sync` workflow. Fixed (now points at a new `backend/README.md`).

## Test suite

Backend: 2700+ tests as of RC1, unchanged in this milestone (no backend
business logic was touched). Frontend: several hundred tests across
unit, component, and real-router integration suites, built up
incrementally across all 9 frontend milestones. See
`docs/release/RELEASE_CHECKLIST_V1.md` §6 for exact figures from the
verification run backing this release.

## Upgrading

There is no prior full-stack release to upgrade from — v1.0.0 is the
first. If you have an existing RC1 (backend-only) deployment, see
`docs/release/UPGRADE_GUIDE_V1.md`.

## Known limitations

See `docs/release/KNOWN_LIMITATIONS.md` for the full, current list
(extended in this milestone with frontend-specific items). Headline
items unchanged from RC1: no live market data or broker integration, no
distributed rate limiting/idempotency implementation, `/ws` is
single-process only. New in v1.0.0: an unpatched ChromaDB advisory
(mitigated at the deployment level, tracked for a future dependency
upgrade); several frontend UI-consistency and accessibility items
explicitly deferred as out of this milestone's bounded scope (documented
in `docs/frontend/MILESTONE_9.md` §7 and carried forward here).

## What's explicitly out of scope for v1.0.0

Per this milestone's own constraints: no new investment features, no
business logic changes (recommendation, strategy, risk algorithms
untouched), no API contract changes, no new telemetry/analytics vendor.
These are possible future directions (see this release's roadmap in the
completion report), not gaps in this release.
