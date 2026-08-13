# MarketMind AI — Release Checklist (v1.0.0)

Produced by Milestone 10, the release-engineering milestone. This
**extends** `docs/release/RELEASE_CHECKLIST.md` (RC1, backend/API/
WebSocket) — run both; this one adds everything new for the full-stack
v1.0.0 release: the frontend, and cross-cutting release-engineering
items (CI/CD, Docker, full-stack security/docs).

## 1. Backend verification

Unchanged from RC1 — work through `docs/release/RELEASE_CHECKLIST.md`
§1-11 in full. No backend business logic, API contract, or database
schema changed in this milestone.

- [ ] `docs/release/RELEASE_CHECKLIST.md` completed in full.
- [ ] `backend/pyproject.toml`'s `readme` fix verified: `pip install
      --dry-run .` (or `uv sync`) from `backend/` completes metadata
      generation without the "Readme path must be within the project
      directory" error.
- [ ] `GET /api/v1/version` reports `"application_version": "1.0.0"`.

## 2. Frontend verification

- [ ] `npm run typecheck` — zero errors.
- [ ] `npm run lint` — zero errors/warnings (`--max-warnings 0`).
- [ ] `npm run test` — zero failures (rerun any failure in isolation
      before treating it as real; this suite has shown transient
      worker-pool/timeout flakiness under heavy parallel load in this
      project's own history — never a code problem when it doesn't
      reproduce in isolation).
- [ ] `npm run build` — succeeds and produces `frontend/dist/`.
- [ ] A production build with `VITE_API_BASE_URL`/`VITE_WS_BASE_URL`
      unset throws a clear error the moment the page loads in a browser
      (open the built `dist/index.html` via a static server and check
      the console) — confirms environment validation is actually wired
      up, not just present in source.

## 3. API verification

Unchanged from RC1 — `docs/release/RELEASE_CHECKLIST.md` §8 (OpenAPI).
No endpoint added, removed, or changed in this milestone.

- [ ] `docs/release/API_CONTRACT_V1.md` still matches the deployed
      OpenAPI schema (it should — nothing changed).

## 4. WebSocket verification

Unchanged from RC1 — `docs/release/RELEASE_CHECKLIST.md` §4-5 cover
`/ws` indirectly via startup/shutdown. Additionally for this release:

- [ ] Frontend connects to `/ws` successfully against a real backend
      and the notification bell/connectivity banner update live when a
      real event (e.g. a backtest completing) is triggered.
- [ ] Killing the backend process disconnects the frontend visibly
      (connectivity banner shows "unavailable") and reconnects
      automatically once the backend is back up.

## 5. Accessibility

Verified in Milestone 9, not re-audited from scratch here (no
accessibility-relevant code changed in Milestone 10).

- [ ] `docs/frontend/MILESTONE_9.md` §1 reviewed — keyboard navigation,
      focus management, live regions, color contrast, semantic HTML.
- [ ] Spot-check: every page reachable via keyboard alone (Tab/Shift+Tab/
      arrow keys where applicable), no keyboard trap.

## 6. Performance

- [ ] `npm run build` output reviewed — the Recharts core chunk
      (`CategoricalChart-*.js` or similar) is a separately-loaded chunk,
      not part of the eagerly-loaded entry bundle (confirms Milestone 9's
      lazy-loading is intact).
- [ ] Backend: `docs/release/RELEASE_CHECKLIST.md` §10 (performance
      benchmarks) — unchanged from RC1.
- [ ] New in this milestone: frontend boot-timing marks
      (`marketmind:boot-start`/`marketmind:app-shell-mounted`/
      `marketmind:boot-to-shell`) visible in browser DevTools'
      Performance panel on a real page load.

## 7. Security

- [ ] `docs/release/SECURITY_REVIEW_V1.md` reviewed in full.
- [ ] `docs/release/SECURITY_CONSIDERATIONS.md` (RC1, backend) still
      reviewed — unchanged.
- [ ] `npm audit` — zero vulnerabilities (or every finding triaged and
      accepted).
- [ ] `pip-audit` (or equivalent) run against the backend's resolved
      dependencies — the known `chromadb` finding (`PYSEC-2026-311`)
      acknowledged, and its mitigation (ChromaDB's port not published
      outside the Docker network) actually applied for this deployment
      if using `docker-compose.prod.yml`.
- [ ] Frontend nginx security headers present on a real response
      (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
      `Permissions-Policy`) — matches the backend's own baseline.
- [ ] No secret present anywhere in `frontend/` — confirmed only
      `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` are ever read.

## 8. Documentation

- [ ] `docs/release/INSTALLATION_GUIDE.md`, `DEPLOYMENT_GUIDE.md`,
      `ADMINISTRATOR_GUIDE.md`, `USER_GUIDE.md`,
      `TROUBLESHOOTING_GUIDE.md` reviewed for accuracy against the
      actual deployed system.
- [ ] `docs/architecture/ARCHITECTURE_OVERVIEW.md` reviewed.
- [ ] `docs/release/RELEASE_NOTES_V1.md` accurately describes what's
      shipping.
- [ ] `docs/release/KNOWN_LIMITATIONS.md` still accurate.
- [ ] `docs/release/UPGRADE_GUIDE_V1.md` reviewed if upgrading an
      existing RC1 deployment.

## 9. Deployment

- [ ] `frontend/Dockerfile` builds successfully with real
      `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` build args.
- [ ] `backend/Dockerfile` builds successfully.
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml
      up --build` brings up the full stack (Postgres, Redis, ChromaDB,
      backend, frontend) and every service reports healthy.
- [ ] Plain `docker compose up -d` (no `-prod` overlay) still behaves
      exactly as documented in `README.md`/
      `docs/release/INSTALLATION_GUIDE.md` — infra-only, unaffected by
      this milestone's additions.
- [ ] `.github/workflows/frontend-ci.yml`, `backend-ci.yml`,
      `release.yml` present and syntactically valid; a real push/PR
      triggers the CI workflows successfully at least once before
      relying on them as a merge gate.
- [ ] A tagged push (`v1.0.0`) triggers `release.yml` and produces
      named artifacts (`frontend-dist-v1.0.0`, `backend-dist-v1.0.0`,
      `docker-images-v1.0.0`).

## 10. Rollback plan

- **Backend**: redeploy the previous image/build. No schema change
  shipped with this release, so no migration rollback is needed.
- **Frontend**: since the frontend is a static artifact, rollback is
  redeploying the previous build's `dist/` output (or previous Docker
  image tag) — instantaneous, no data implications. If this is the
  *first* frontend deployment (adopting v1.0.0 from an RC1 backend-only
  deployment), "rollback" is simply taking the frontend back down; the
  backend is unaffected either way since the frontend has no
  server-side state of its own.
- **Both**: because the frontend and backend communicate only through
  the frozen `/api/v1`/`/ws` contract, the two can be rolled back
  independently without coordination — confirm this remains true for
  any *future* release before relying on it (a release that changes the
  contract would need both sides rolled back together).

## Sign-off

| Item | Status | Notes |
|---|---|---|
| Backend verification | | |
| Frontend verification | | |
| API verification | | |
| WebSocket verification | | |
| Accessibility | | |
| Performance | | |
| Security | | |
| Documentation | | |
| Deployment | | |
| Rollback plan reviewed | | |

Record who ran this checklist, against which environment, and the date,
before promoting a build to production.
