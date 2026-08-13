# MarketMind AI — Security Review (v1.0.0)

Milestone 10's full-stack security review. **Extends**
`docs/release/SECURITY_CONSIDERATIONS.md` (RC1, backend-only) — read
that first; this document only covers what's new for v1.0.0: the
frontend's own security posture, and a dependency audit across both
halves of the app. Nothing in the backend's authentication,
authorization, or API security model changed for this milestone (no API
contract changes, per this milestone's own constraints).

## Content Security Policy

**Backend**: unchanged from RC1 — disabled by default
(`SECURITY_HEADERS_CONTENT_SECURITY_POLICY` unset), because a strict
default would break `/docs`/`/redoc`'s CDN-loaded assets. See
`docs/release/SECURITY_CONSIDERATIONS.md`.

**Frontend**: also disabled by default, for the analogous reason —
`frontend/nginx.conf` deliberately omits a `Content-Security-Policy`
header rather than shipping one that hasn't been tuned to this
deployment's actual origins. A safe default CSP is hard to write
generically because it must allow `connect-src` to reach whatever this
specific build's `VITE_API_BASE_URL`/`VITE_WS_BASE_URL` resolve to
(baked in at build time, different per deployment) plus Recharts/Framer
Motion's own inline style usage. Recommended for a real production
deployment, added directly to `frontend/nginx.conf`:

```nginx
add_header Content-Security-Policy "default-src 'self'; connect-src 'self' https://api.example.com wss://api.example.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:;" always;
```

(Replace the `connect-src` origins with this build's actual
`VITE_API_BASE_URL`/`VITE_WS_BASE_URL` origins.) Not enabled by default
here for the same reason the backend leaves HSTS/CSP off by default —
an untuned value shipped as "the default" would break real deployments
in ways that are hard to debug, worse than not having it.

## HTTP security headers

**Backend**: unchanged from RC1 — `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` always sent;
CSP/HSTS opt-in. See `docs/release/SECURITY_CONSIDERATIONS.md`.

**Frontend**: `frontend/nginx.conf` now sends the same 4 always-on
headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: geolocation=(), microphone=(), camera=()`) —
matching the backend's own values exactly, so both halves of the app
present one consistent security baseline regardless of which origin a
request lands on. HSTS is not sent by nginx either — enable it at
whatever reverse proxy/load balancer actually terminates TLS in front
of this container (this image does not terminate TLS itself, same as
the backend).

## Token storage

Unchanged — this milestone made no API or auth-flow changes.
Access/refresh tokens are stored in `localStorage` or `sessionStorage`
(chosen by the user's "Remember me" preference at login —
`src/store/auth-store.ts`), not an `httpOnly` cookie. This is a real,
already-accepted trade-off from the authentication architecture
(`docs/architecture/AUTHENTICATION_ARCHITECTURE.md`), not something
this milestone could change without an API contract change (cookie-based
auth requires the backend to set the cookie, which `POST /auth/login`
does not do today) — explicitly out of scope
("Do NOT modify API contracts"). Consequence, documented plainly:
these tokens are readable by any JavaScript running on the page, so an
XSS vulnerability anywhere in the app would be able to exfiltrate them
— this is why `Content-Security-Policy` (above) and keeping
`ACCESS_TOKEN_EXPIRE_MINUTES` short (backend default: 60 minutes,
`docs/release/SECURITY_CONSIDERATIONS.md`) both matter.

## Sensitive data exposure

Verified, not new: `/profile` (Milestone 8) never renders a raw
access/refresh token value — only `AccessToken`/`RefreshToken` metadata
(`issued_at`/`expires_at`). Verified, not new: no `console.log`/
`console.debug`/`console.info` call anywhere in the frontend logs a
token or password value (repo-wide search, zero matches). The backend's
own `handle_unhandled_exception` never leaks internals to the client
(`docs/release/SECURITY_CONSIDERATIONS.md`) — unchanged.

## Dependency audit

**Frontend** (`npm audit`, `frontend/package-lock.json`): **0
vulnerabilities** across 368 packages.

**Backend** (`pip-audit` against the dependencies declared in
`backend/pyproject.toml`):

| Package | Version | Advisory | Fixed in | Notes |
|---|---|---|---|---|
| `chromadb` | 1.5.9 | `PYSEC-2026-311` | none yet | Pre-authentication code-injection on ChromaDB's own `/api/v2/.../collections` endpoint via a malicious model repository + `trust_remote_code=true`. This application's own code never sets `trust_remote_code`, but the vulnerable surface is ChromaDB's own server, reachable by anyone who can reach its port — mitigated by **not publishing ChromaDB's port publicly** (`docker-compose.prod.yml` now overrides `postgres`/`redis`/`chromadb` to `ports: !reset []`; only the `backend` container can reach them, over the internal Docker network). Note: a plain `ports: []` override does *not* achieve this — `ports` is a Compose "unique resource" key, so an empty override is ignored and the base file's published ports still merge in; `!reset` is the tag that actually clears an inherited sequence. No fixed `chromadb` version exists yet to upgrade to — track this advisory and upgrade when one ships. |

`pip` itself (the package manager, 25.0.1, used only to install
dependencies in this local verification environment) reported several
advisories — **not a project dependency** (`pyproject.toml` never
declares `pip` as one), and not shipped inside the runtime Docker image
beyond the build stage, which uses whatever `pip` ships with the
`python:3.13-slim` base image. Not a finding about this application.

## Client-side secret handling

Verified: the frontend reads exactly 2 environment variables anywhere
in its source (`VITE_API_BASE_URL`, `VITE_WS_BASE_URL` —
`src/services/api/config.ts`) — both are URLs, neither is a secret.
Repo-wide search for `ANTHROPIC_API_KEY`/`SECRET_KEY`/
`POSTGRES_PASSWORD` (the backend's actual secrets) in `frontend/src`
found zero references to their *values* (only 2 code comments
explaining a `503` response, which name the setting but never read it).
There is no mechanism by which a backend secret could end up compiled
into the frontend bundle — Vite only inlines variables explicitly
prefixed `VITE_` and explicitly read via `import.meta.env`, and no
`VITE_`-prefixed secret exists anywhere in `.env.example` or
`frontend/.env.example`.

## Summary

| Area | Status |
|---|---|
| CSP | Reviewed; deliberately disabled by default on both halves (documented how to enable) |
| HTTP security headers | Frontend now matches backend's existing baseline |
| Token storage | Unchanged, documented trade-off (XSS exposure, mitigated by CSP + short token expiry) |
| Sensitive data exposure | Verified clean |
| Dependency audit — frontend | 0 vulnerabilities |
| Dependency audit — backend | 1 real finding (`chromadb` PYSEC-2026-311) — mitigated at the deployment level (port no longer published) |
| Client-side secret handling | Verified clean — only 2 non-secret URLs are ever read |
