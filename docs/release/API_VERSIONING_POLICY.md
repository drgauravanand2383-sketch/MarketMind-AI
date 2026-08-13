# MarketMind AI — API Versioning Policy

**`/api/v1` is frozen as of RC1** (Sprint 60). Every element documented
in `docs/release/API_CONTRACT_V1.md` — request schemas, response
envelopes, status codes, error format, permission requirements — is
covered by this policy.

## What "frozen" means

No breaking change may be made to `/api/v1` after RC1. A change is
breaking if it would require an existing, correctly-written client to
change its code. Concretely, breaking changes include:

- Removing or renaming a path, an operation, a request field, or a
  response field.
- Changing a field's type or making an optional field required.
- Changing a status code an endpoint returns for a case it already
  handles.
- Changing the meaning of an existing `error` code, or removing one from
  the closed set (`not_found`, `method_not_allowed`, `service_unavailable`,
  `conflict`, `domain_error`, `validation_error`, `http_error`,
  `internal_error`).
- Changing a permission string an endpoint already requires, or adding a
  new required permission to an existing endpoint.
- Changing `/ws`'s message protocol (`docs/architecture/WEBSOCKET_FRAMEWORK.md`
  §5) — the `action`/`type` vocabulary, or an existing event's `payload` shape.

## What is allowed without a version bump

Purely additive, backward-compatible changes:

- A new endpoint.
- A new optional request field with a sensible default.
- A new response field (existing clients that don't read it are
  unaffected — this is why every response schema still uses `extra="forbid"`
  only on *requests*, never on responses).
- A new event type on `/ws`.
- A new permission string protecting a *new* endpoint.
- Fixing an actual production defect in a response that was already
  wrong relative to its own documented shape (a bug fix, not a contract
  change) — requires explicit user sign-off per this sprint's own
  constraint ("Do NOT modify business logic unless absolutely required
  to fix a production defect").

## How a breaking change gets made

Never in-place. A breaking change to anything `/api/v1` already does
requires a sibling `/api/v2` package (`app/api/v2/`, its own `router.py`,
schemas, dependencies — mirroring `/api/v1`'s own structure) mounted
alongside `/api/v1` in `app/main.py`, exactly as `docs/architecture/API_ARCHITECTURE.md`
§2 already specifies for Sprint 55's own future-versioning intent. Existing
`/api/v1` consumers must keep working, unmodified, for as long as `/api/v1`
is supported — see the deprecation window below.

## Deprecation window

Once `/api/v2` exists and a client has a documented migration path,
`/api/v1` enters a deprecation window before removal. This project has
not yet reached that point (RC1 *is* v1's initial freeze) — the specific
window length is a product decision for whoever ships the first `/api/v2`,
not fixed by this document. At minimum: `/api/v1` must remain fully
functional (not just present but unmaintained) for the entire window,
and its deprecation must be announced in that release's own release
notes, not silently.

## `/ws` versioning

The WebSocket framework has no separate version number — it versions
alongside `/api/v1` implicitly, since every event's `payload` reuses an
`/api/v1`-exposed domain model directly. A breaking `/api/v2` would
require its own `/ws/v2` (or equivalent) only if its domain models
themselves changed shape; a `/api/v2` that only adds new REST endpoints
without touching existing payload shapes needs no corresponding `/ws`
change.
