# MarketMind AI — Authentication & Authorization Framework

Produced by Sprint 56, Phase 2. Covers `app/auth/` — provider-agnostic
authentication (JWT is the first, and so far only, provider) and RBAC
authorization with role hierarchy. Independent from the API layer: `app/api/`
consumes this framework through dependency injection
(`app.auth.dependencies`); this framework never imports from `app/api/`.

No business logic from any domain engine (Screening through Explainability)
was modified. No broker authentication, OAuth providers, social login,
SSO, billing, or multi-tenancy exist anywhere in this framework.

## 1. Package Layout

```
app/auth/
  models/          Domain — User, Role, Permission, tokens, principal
  security/          Clock, password hashing, JWT signing, secret loading
                       — each an abstraction with one stdlib-only impl
  repositories/        BaseAuthRepository (ABC) + postgres/ (concrete)
  providers/             AuthenticationProvider (ABC) + JwtAuthenticationProvider
  services/                AuthenticationService (provider-agnostic facade +
                            registration), AuthorizationService (RBAC resolution)
  policies/                  Pure, HTTP-independent Policy objects + PolicyEvaluator
  middleware/                  AuthenticationMiddleware — resolves a bearer
                                token, never authorizes
  dependencies/                  FastAPI providers app/api/ consumes
  exceptions.py                   One shared exception hierarchy
```

Tests live at `backend/tests/auth/` (mirroring the `app/auth/` subpackage
layout), not inside `app/auth/` itself — the one place this sprint's own
literal architecture list was read as directional rather than literal,
to stay consistent with every other domain package in this codebase
(Sprints 44-55 all keep tests under `backend/tests/`).

## 2. Authentication Architecture

Three layers, each depending only on the abstraction below it:

```
app/auth/dependencies    (FastAPI-flavored; consumed by app/api/)
        v
app/auth/services.AuthenticationService   (provider-agnostic facade)
        v
app/auth/providers.AuthenticationProvider (ABC)  <-- JwtAuthenticationProvider (concrete)
        v
app/auth/security  (clock, password hashing, JWT signing)
app/auth/repositories  (BaseAuthRepository ABC -> PostgresAuthRepository)
```

`AuthenticationService` holds one injected `AuthenticationProvider` and
delegates every operation to it (`authenticate`, `issue_token`,
`refresh`, `revoke`, `validate`, `get_current_user`) — it contains no
JWT-specific logic itself. This is what "provider-agnostic" means
concretely: swapping the concrete provider is a one-function change in
`app.bootstrap.build_authentication_provider`; nothing above that layer
changes. `AuthenticationService` also owns user *registration*
(`register()`) — a repository+policy concern (password strength,
duplicate username/email), not a provider concern, since a future
OAuth2/SSO provider wouldn't register local password credentials at all.

## 3. Provider Abstraction

`AuthenticationProvider` (ABC, `app/auth/providers/provider.py`) declares
exactly the eight methods this sprint's own spec names:
`authenticate`, `issue_token`, `refresh_token`, `revoke_token`,
`validate_token`, `get_current_user`, `provider_name`, `health`.

`authenticate()`'s credential shape is intentionally provider-specific —
`JwtAuthenticationProvider.authenticate(username, password)` checks a
local password hash; a future `OAuth2AuthenticationProvider` would accept
an authorization code and exchange it with an external IDP instead. Each
concrete provider defines its own dependencies via its own constructor
(`JwtAuthenticationProvider` needs `BaseAuthRepository`+`BaseJWTSigner`+
`BasePasswordHasher`+`AuthorizationService`; a future provider needs
whatever it needs) while still satisfying the same ABC contract.

`health()` returns `app.operations.health.models.DependencyHealth`
(Sprint 54) directly — reused, not a second health model.

## 4. RBAC Model

Built-in role *names* (`app.auth.models.role.BuiltinRole`): `ADMIN`,
`ANALYST`, `VIEWER`, `API_CLIENT`. This framework seeds no `Role`
instances, no permission catalog, and no hierarchy — there is no fixed
permission taxonomy to assign one from. A deployment constructs and
persists its own `Role` rows (choosing names, permissions, and parent
chain) via `BaseAuthRepository.create_role()`.

**Role hierarchy / permission inheritance.** `Role.parent_id` (additive
— not in this sprint's own literal field list, flagged and documented in
`app.auth.models.role`'s own docstring, the same established pattern
every earlier sprint used for a structurally-necessary field) lets one
role inherit everything its parent grants, recursively.
`AuthorizationService.resolve_effective_permissions(user)` walks a
user's own `roles` (a tuple of `Role.id` values) and each one's
`parent_id` chain, unioning every permission found — cycle-safe (a
`parent_id` loop, a data error this framework doesn't prevent at write
time, stops resolving once a role id is revisited rather than recursing
forever).

A user's effective permission set = their own directly-granted
`User.permissions`, union every permission (recursively) granted by
every role in `User.roles`.

**Where resolution happens vs where checking happens** — this is the
one design decision worth calling out explicitly: `AuthorizationService`
is the *only* place in this framework that does I/O or hierarchy-walking
for authorization purposes, and it runs exactly once, at token-issuance
time (`JwtAuthenticationProvider._issue_pair`/`refresh_token`). The
result — flattened role *names* and effective permission *names* — is
embedded directly in the access token's claims and carried on
`AuthenticatedPrincipal`. Every `app.auth.policies.Policy` downstream of
that only ever compares against the already-resolved
`AuthenticatedPrincipal.roles`/`.permissions` in memory — no repository,
no I/O, no hierarchy-walking. This is *why* "Policies must remain
reusable outside HTTP" is actually true in this codebase, not just
asserted: a policy needs nothing but a principal object to evaluate.

## 5. Authorization Policies

`app.auth.policies.policy.Policy` (ABC) — `evaluate(principal) -> bool`,
synchronous, pure. Five implementations: `RequireAuthenticated`,
`RequireRole`, `RequireAnyRole`, `RequirePermission`,
`RequireAllPermissions`. All five return `False` for `principal=None`
(never raise on missing authentication — the caller decides what to do
with a `False`).

`PolicyEvaluator.evaluate(policy, principal) -> bool` /
`.check(policy, principal) -> None` (raises `AuthorizationDeniedError`)
is the tiny orchestrator that runs a policy — it contains no policy logic
of its own.

`app.auth.dependencies.policy_guard.require_policy(policy)` is the *only*
place a policy failure becomes an HTTP status code: `401` when there is
no authenticated principal at all, `403` when the principal is
authenticated but the policy denies. Every protected endpoint added since
Sprint 57 (`/watchlists/*`, `/portfolio/*`, and Sprint 58's
`/research/*`, `/screening/*`, `/signals/*`, `/alerts/*`, `/strategies/*`,
`/backtests/*`, `/explainability/*`) uses it via
`dependencies=[Depends(require_policy(...))]`.

**OpenAPI Bearer metadata (Sprint 58).** `require_policy`'s returned
dependency also declares `Security(bearer_scheme)`
(`bearer_scheme = HTTPBearer(auto_error=False)`, module-level in
`policy_guard.py`) purely so FastAPI populates
`components.securitySchemes` and each protected operation's `security`
field — this is what gives Swagger UI its Authorize button. It is *only*
OpenAPI metadata: `auto_error=False` means it never itself raises or
inspects the credential, so token verification is still done exclusively
by `AuthenticationMiddleware` + the 401/403 checks described above — no
authentication logic is duplicated. See
`docs/architecture/INTELLIGENCE_API.md` §1 for the full rationale.

## 6. JWT Lifecycle

**Claim shape.** Every token (access or refresh) carries `sub` (user id),
`typ` (`"access"`/`"refresh"` — prevents a refresh token from being
accepted where an access token is required, and vice versa), `jti`
(a UUID identifying this specific issued token, for revocation), `iat`,
`exp` (unix timestamps). An access token additionally carries `username`,
`roles` (names), and `permissions` (effective, hierarchy-resolved) —
embedded at issuance so `validate_token()` is a fast, stateless,
single-signature-check operation with no repository lookup beyond a
revocation check, suitable for per-request middleware use. A refresh
token carries none of that — only enough to identify its subject.

**The staleness tradeoff, stated plainly:** a role/permission change does
not take effect for an already-issued access token until it expires or
its holder refreshes. This is standard JWT behavior, not a bug, bounded
by `AuthSettings.access_token_expire_minutes` (default 60). `refresh_token()`
*does* re-resolve permissions from the repository at refresh time, so a
role change takes effect on the next refresh even though it never retroactively
changes an already-issued access token.

**Signing.** HS256 (HMAC-SHA256), implemented against the standard
library only (`app.auth.security.jwt_signer.HmacJWTSigner`) — no
`pyjwt`/`python-jose` dependency. See §7 for why, and for the specific
security properties this implementation guarantees.

## 7. Token Rotation

Every successful `refresh_token()` call revokes the *presented* refresh
token (`BaseAuthRepository.revoke_token_id`) before issuing a new
access/refresh pair. A refresh token is therefore usable exactly once:
whoever presents it first (the legitimate holder, or an attacker who
stole it) gets a fresh pair; a second attempt with the same (now-revoked)
token fails with `TokenRevokedError` — a detectable signal that the token
was used more than once, which a real deployment's monitoring can alert
on as a likely compromise indicator. `revoke_token()` is also exposed
directly (used by, e.g., a logout flow) and is a defensible no-op against
an already-expired token — revoking something that can no longer be used
anyway is not an error.

## 8. Security Model

- **Password hashing** — PBKDF2-HMAC-SHA256, 600,000 iterations by
  default, standard library only (`hashlib.pbkdf2_hmac`,
  `secrets.token_bytes` for a fresh salt per hash, `hmac.compare_digest`
  for constant-time verification). Self-describing hash format
  (`pbkdf2_sha256$<iterations>$<salt>$<hash>`) — a future iteration-count
  increase applies to newly-hashed passwords without invalidating
  already-stored ones, since `verify()` reads the count from the stored
  hash, never from the hasher's own current default.
- **JWT signing** — HS256 only, `hmac.compare_digest` for signature
  verification (never `==`), the token's own header `alg` is checked
  against the *configured* algorithm and rejected otherwise (no `alg:
  none` / algorithm-confusion path exists — see
  `app.auth.security.jwt_signer`'s own docstring for the full threat
  model this addresses).
- **No new third-party cryptography dependency** — both of the above use
  only the Python standard library, consistent with this whole
  codebase's discipline (Sprints 44-55 never added a dependency beyond
  what `pyproject.toml` already declared) and with CLAUDE.md's own rule
  that new technologies require approval.
- **Secret loading** — `AuthSettings.secret_key` is a `pydantic.SecretStr`
  (never appears in a `repr()`/log line); `app.auth.security
  .secrets_loader.load_jwt_secret` is the single place `.get_secret_value()`
  is ever called on it, at bootstrap time only.
- **No plaintext password persistence** — `User` (the domain model) has
  no password field at all; `BaseAuthRepository.create_user()` takes an
  already-hashed string as a separate parameter, and
  `get_password_hash()` is the only way to read it back — never exposed
  through `User` itself.
- **No username enumeration via `authenticate()`** — an unknown username
  and a correct-username-wrong-password both raise the exact same
  `InvalidCredentialsError` with the exact same message. Password
  correctness is checked *before* account-status (`ACTIVE`/`DISABLED`/
  `LOCKED`/`PENDING`) is checked, so a wrong password never reveals
  whether an account exists and is merely inactive.
- **Clock abstraction** — every expiry/clock-skew decision goes through
  an injected `BaseClock`, never `datetime.now()` directly — this is what
  makes clock-skew and expiry behavior deterministically testable (no
  real `time.sleep` anywhere in this framework's own test suite).

## 9. Future OAuth2 Integration

Implement `app.auth.providers.provider.AuthenticationProvider` as a new
`OAuth2AuthenticationProvider` (its own module, its own constructor
dependencies — likely an HTTP client for the external IDP's token
endpoint, not `BaseAuthRepository`/`BasePasswordHasher` at all for the
credential-exchange step, though it would still use
`BaseAuthRepository` to persist/look up the local user record an
external identity maps to). Wire it in via
`app.bootstrap.build_authentication_provider` — `AuthenticationService`
and everything above it needs no change. `AuthSettings` gains whatever
OAuth2-specific configuration that provider needs (client id/secret,
authorization/token endpoint URLs), following the same
`pydantic_settings.BaseSettings` pattern every other settings section
already uses.

## 10. Future SSO Integration

Same extension point as OAuth2 (§9) — SSO (SAML or an OIDC-based
enterprise IDP) is, from this framework's perspective, another
`AuthenticationProvider` implementation with its own credential-exchange
mechanics. If multiple providers need to coexist simultaneously (e.g.
local JWT login *and* enterprise SSO, chosen per-request or per-tenant),
`AuthenticationService` would need to hold a small provider *registry*
keyed by provider name (mirroring `app.providers.registry.ProviderRegistry`,
already established elsewhere in this codebase) rather than a single
injected provider — a real, but bounded, extension to
`AuthenticationService`'s own constructor, not a rewrite.

## 11. Future API Key Provider

A machine-to-machine credential (long-lived, not a short-lived JWT) is
also naturally another `AuthenticationProvider` implementation —
`authenticate()` would look up a hashed API key (via
`BaseAuthRepository`, the same "never persist the plaintext credential"
discipline §8 already establishes for passwords) rather than a username/
password pair, and `issue_token()`/`refresh_token()` may be no-ops or
raise "not supported for this provider" for a provider whose whole point
is a single long-lived credential rather than a rotating token pair.
`BuiltinRole.API_CLIENT` already names the role such API-key-authenticated
callers would typically hold.
