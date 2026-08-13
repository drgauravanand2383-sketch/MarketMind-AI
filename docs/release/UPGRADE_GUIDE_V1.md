# MarketMind AI — Upgrade Guide (RC1 → v1.0.0)

Practical steps. See `docs/release/UPGRADE_POLICY.md` for the versioning
*rules* this and every future release follows — this document is the
*steps* for this specific upgrade.

## Who needs this

Anyone running an existing RC1 (backend-only) deployment. If you're
installing MarketMind AI for the first time, use
`docs/release/INSTALLATION_GUIDE.md` or
`docs/release/DEPLOYMENT_GUIDE.md` instead — there's nothing to
"upgrade" yet.

## What changed

- **No backend business logic, API contract, or database schema
  changed.** `/api/v1` and `/ws` are exactly as documented in
  `docs/release/API_CONTRACT_V1.md` — no new Alembic migration ships
  with this release, so there is nothing to run beyond your normal
  deployment process.
- **`backend/pyproject.toml`'s `readme` field changed** from
  `../README.md` to `README.md` (a new `backend/README.md` was added).
  This only affects building/installing the backend package
  (`pip install .` / `uv sync`) — it has no runtime effect. If your
  deployment process builds the backend from source, pull the latest
  `backend/pyproject.toml` and `backend/README.md` together.
- **`APPLICATION_VERSION`/`app.main`'s reported version** changed from
  `0.1.0` to `1.0.0` (`GET /api/v1/version`'s `application_version`
  field, and the OpenAPI schema's `info.version`). No behavioral change
  — purely the version string itself.
- **The frontend is new** — RC1 had no frontend at all. Deploying it is
  purely additive: see `docs/release/DEPLOYMENT_GUIDE.md` §11. It talks
  to your existing backend over the same `/api/v1`/`/ws` contract RC1
  already shipped; no backend changes are required to support it.

## Steps

1. Pull the new backend source (`app/main.py`, `app/api/v1/routers/
   version.py`, `backend/pyproject.toml`, new `backend/README.md`).
2. If you build the backend from source as part of your deployment,
   re-run that build — the `readme` field fix means a build that was
   previously failing (if you'd already hit modern `hatchling`'s
   validation) will now succeed; a build that was already working some
   other way (e.g. a pre-built wheel, or an older `hatchling`) is
   unaffected either way.
3. Restart the backend. `GET /api/v1/version` should now report
   `"application_version": "1.0.0"`.
4. Deploy the frontend for the first time — see
   `docs/release/DEPLOYMENT_GUIDE.md` §11. Point `VITE_API_BASE_URL`/
   `VITE_WS_BASE_URL` at your existing, already-running backend.
5. Review `docs/release/SECURITY_REVIEW_V1.md` and consider applying
   the `docker-compose.prod.yml` port-publication hardening
   (`postgres`/`redis`/`chromadb` no longer publish host ports) if
   you're adopting `docker-compose.prod.yml` for the first time.
6. Work through `docs/release/RELEASE_CHECKLIST_V1.md` before
   considering the upgrade complete.

## Rollback

Since no schema or API contract changed, rolling back is simply
redeploying the previous backend build (RC1) and, if you'd deployed the
new frontend, taking it back down or pointing it elsewhere — there is no
database state introduced by this release that would need reverting.
