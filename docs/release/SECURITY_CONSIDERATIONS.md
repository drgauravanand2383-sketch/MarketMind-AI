# MarketMind AI — Security Considerations (RC1)

## Authentication

Bearer JWT, issued by the Authentication & Authorization Framework
(Sprint 56 — `docs/architecture/AUTHENTICATION_ARCHITECTURE.md`).
`SECRET_KEY` signs every token — **rotate it, and invalidate every
existing token, if it is ever suspected leaked.** There is no token
revocation list in RC1: a leaked, still-unexpired access token remains
valid until its own expiry (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 60
minutes) — keep this short in production, and rely on refresh-token
rotation for longer sessions rather than long-lived access tokens.

`/ws` authenticates the same way, via a `token` query parameter or
`Authorization` header on the handshake — a query-parameter token can
end up in server access logs and browser history. If this is a concern
for your deployment, ensure your reverse proxy/access-log configuration
redacts query strings on `/ws`, or prefer the `Authorization` header
(supported by non-browser WebSocket clients) where possible.

## Authorization

Every protected endpoint requires a specific permission string,
evaluated via `PolicyEvaluator`/`RequirePermission` — no inline role
checks anywhere (verified by code review across every router this and
prior sprints built). There is no permission-string registry/enum — a
typo in a new endpoint's required permission would silently create an
unreachable permission (nobody has it) rather than fail loudly; review
any new permission string against the existing catalog in
`docs/architecture/{WATCHLIST_PORTFOLIO_API,INTELLIGENCE_API,
WEBSOCKET_FRAMEWORK}.md` before shipping one.

## Transport security

This application does not terminate TLS — it must be deployed behind a
TLS-terminating reverse proxy in production. `Strict-Transport-Security`
is **disabled by default** specifically so a plain-HTTP development
server never sends it (a browser that received HSTS over HTTP would
remember it and start refusing plain HTTP entirely, including for local
development) — enable `SECURITY_HEADERS_HSTS_ENABLED=true` only once the
deployment is genuinely served over HTTPS end-to-end.

## Content Security Policy

Disabled by default for the same reason: FastAPI's own `/docs` (Swagger
UI) and `/redoc` pages load JS/CSS from a CDN, and a strict default CSP
would break them. If you enable `SECURITY_HEADERS_CONTENT_SECURITY_POLICY`,
either scope it to exclude `/docs`/`/redoc`, self-host the Swagger/ReDoc
assets, or disable the docs pages in production (FastAPI's `docs_url`/
`redoc_url` constructor arguments — not currently wired to a setting in
RC1; a future sprint could add one).

## Secrets

`SECRET_KEY`, `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY`, `REDIS_PASSWORD`
all have insecure development defaults or none at all —
`ConfigurationValidationService` flags an unchanged default as a
`WARNING` at startup (advisory, non-blocking — review every warning
before promoting a build, per `docs/release/RELEASE_CHECKLIST.md`).
Never commit `.env`; `.env.example` documents every field with a clearly
fake placeholder value.

## Rate limiting & idempotency — not yet enforced

RC1 ships **interfaces only** for both (Sprint 60's own explicit scope).
No request is actually rate-limited or deduplicated by anything in this
release. If your deployment is internet-facing, put rate limiting at
the edge (reverse proxy, API gateway, WAF) until a concrete
`RateLimiter`/`IdempotencyStore` implementation exists — do not assume
this application protects itself.

## Input validation

Every request body is a Pydantic model with `extra="forbid"` — an
unknown field is always rejected (`422`), never silently accepted.
Every path/query identifier is either `uuid.UUID`-typed (automatic
format validation) or pattern-constrained (ticker format). This is
defense against malformed input, not against a determined attacker
crafting valid-shaped-but-malicious payloads (e.g. a very large
`snapshots` list on `POST /backtests`) — there is no request-size or
array-length cap in RC1 beyond what each domain model's own `Field(...)`
constraints (e.g. `min_length=1`) happen to enforce; consider a reverse-
proxy body-size limit for defense in depth.

## Error responses never leak internals

`handle_unhandled_exception` (the last-resort 500 handler) never returns
the raw exception message or a traceback to the client — only a fixed
`"An unexpected error occurred."` string; the real exception is logged
server-side via the structured logger. Every other error path
(`handle_domain_error`, `handle_validation_error`) returns a message
derived from the raised exception's own `str()`, which every domain
exception in this codebase already writes as a safe, user-facing
message (not an internal detail) — confirmed by convention across every
domain package's own exception classes.

## Dependencies

This release introduces no new runtime dependency beyond what earlier
sprints already declared (`pyproject.toml`) — the rate limiting,
idempotency, and security-headers work this sprint is built entirely
from the standard library, Pydantic, and Starlette/FastAPI primitives
already in use.
