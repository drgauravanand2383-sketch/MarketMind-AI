# MarketMind AI Frontend — Architecture (Milestone 1)

Frontend Milestone 1 builds the application shell: the scalable
foundation the product's real features will be built into, capable of
consuming the frozen `/api/v1` REST contract
(`docs/release/API_CONTRACT_V1.md`) and the `/ws` WebSocket protocol
(`docs/architecture/WEBSOCKET_FRAMEWORK.md`). It ships no investment
features of its own — only a Health Dashboard, proving every
infrastructure layer actually works end to end.

## 1. Technology stack

Exactly the stack specified for this milestone — nothing substituted,
nothing added:

| Concern | Library |
|---|---|
| UI framework | React 19 |
| Language | TypeScript (strict, no `any`) |
| Build tool | Vite |
| Server state | TanStack Query |
| Routing | TanStack Router (file-based) |
| Client state | Zustand |
| Styling | TailwindCSS v4 |
| Forms | React Hook Form + Zod |
| Animation | Framer Motion |
| Charts | Recharts (not yet used — no chart-bearing feature exists yet) |
| Testing | Vitest, React Testing Library, MSW |

No HTTP client library (axios, ky, …) was added: `src/services/api/client.ts`
is a hand-rolled `fetch` wrapper, since the approved stack doesn't list
one and "never introduce new technologies without approval" (`CLAUDE.md`)
is read as binding for this choice too.

## 2. Folder structure

```
frontend/src/
  app/          Composition root: providers, the QueryClient, the router
                instance, the theme provider, the generated route tree.
  components/   Small, reusable, presentation-only building blocks
                (ErrorBoundary, LoadingBoundary, ThemeToggle).
  features/     Feature-scoped UI that composes hooks + components into
                a screen's worth of behavior (auth/login-form,
                health/health-dashboard). A feature never reaches into
                another feature's internals.
  hooks/        Reusable React hooks bridging components to
                services/store (use-auth, use-health, use-websocket).
  layouts/      Structural chrome shared across authenticated routes
                (AppShell, Sidebar, TopNav, Footer).
  pages/        File-based route definitions only (TanStack Router's
                `routesDirectory`) — a page file wires a URL to a
                feature/layout component; it holds no business logic of
                its own.
  services/     Framework-agnostic clients for external systems.
    api/        The typed REST client + one thin module per resource
                (auth-api.ts, system-api.ts).
    websocket/  The typed WebSocket client (ws-client.ts).
  store/        Zustand stores — client-owned state only (auth session,
                theme preference).
  styles/       Global Tailwind entry point (globals.css).
  types/        Hand-written TypeScript types mirroring backend Pydantic
                models field-for-field (api.ts, auth.ts, health.ts,
                websocket.ts) — the single source of truth for the
                frontend/backend contract shape.
  test/         Vitest setup, MSW server/handlers/fixtures, shared
                render helpers — never application code.
```

This is Clean Architecture adapted for React: `types` and `services` are
the innermost layer (no React import anywhere in either), `store` and
`hooks` are the application layer (React-aware, but UI-agnostic), and
`components`/`features`/`layouts`/`pages` are the outermost,
UI-only layer. Dependencies only ever point inward — a `service` never
imports a `hook` or a `component`.

## 3. API consumption

### 3.1 The typed client

`src/services/api/client.ts` exports one `ApiClient` class and one
singleton (`apiClient`). Every resource-specific module
(`auth-api.ts`, `system-api.ts`) is a thin set of functions calling
`apiClient.get/post/patch/delete<T>(path, ...)` and returning the
already-unwrapped `T` — no fetch/parsing logic duplicated per resource.

Cross-cutting concerns the client owns, so no call site has to:

- **Request/response interceptors** — `addRequestInterceptor`/
  `addResponseInterceptor`, unused by this milestone but present as an
  extension point (e.g. a future request-id header, or client-side
  telemetry) without touching every call site later.
- **Retry policy** — network errors and a configurable set of retryable
  status codes (`502`/`503`/`504` by default) get exponential-backoff
  retries, capped at `maxRetries`. A caller can opt out per-request
  (`skipRetry`) — used by `systemApi.getReadiness`, since a `503` there
  is a meaningful "not ready" business answer, not a transient failure.
- **401-triggered refresh-and-retry** — on a `401`, the client calls the
  configured `onUnauthorized` hook (wired to `useAuthStore.getState().refresh`
  in `src/app/providers.tsx`) exactly once per request, and retries the
  original request with the new token if refresh succeeded. Concurrent
  401s across simultaneous in-flight requests share one refresh call
  (`refreshInFlight` coalescing) rather than firing a refresh per request.
- **Error normalization** — every non-2xx response becomes a thrown
  `ApiError` (`src/services/api/errors.ts`) carrying the backend's own
  `status`/`code`/`message`/`details` (mirroring
  `docs/release/API_CONTRACT_V1.md` §5's closed error-code set), plus a
  synthetic `network_error`/`parse_error` code for the cases the backend
  never got to respond. Callers branch on `error.status`/`error.code`,
  never on parsing `error.message` strings.

### 3.2 Response envelope types

`src/types/api.ts` mirrors `app.api.v1.schemas.common` exactly:
`SuccessResponse<T>`, `PaginatedResponse<T>`, `ErrorResponse`,
`ValidationErrorResponse`, and the closed `ApiErrorCode` union. Every
other `types/*.ts` module mirrors one backend Pydantic model family the
same way, verified against the actual backend source at the time each
was written (not reconstructed from memory) — see `src/types/auth.ts`,
`src/types/health.ts`, `src/types/websocket.ts`.

### 3.3 The Auth API (backend addition)

`AuthenticationService` (Sprint 56) existed but was never reachable over
HTTP — this milestone needed a login/refresh/logout endpoint to consume,
so a minimal REST router was added at `/api/v1/auth` (a pure, additive
extension to the frozen contract; see
`docs/release/API_CONTRACT_V1.md` §1 and §4 for the exact status-code
and tag conventions it follows). `src/services/api/auth-api.ts` wraps
all three operations; `login`/`refresh` pass `skipAuth: true` since a
possibly-stale token must never be sent on those two calls.

## 4. State management

Server state and client state are kept in two different systems on
purpose, never mixed:

- **TanStack Query** owns anything the backend is the source of truth
  for and that can be refetched: health/readiness/version
  (`src/hooks/use-health.ts`), and the login/logout *mutations*
  (`src/hooks/use-auth.ts`, wrapping Zustand actions in `useMutation` for
  `isPending`/`isError` ergonomics). The default `QueryClient`
  (`src/app/query-client.ts`) never retries a `401`/`403`/`404` — a
  retried request with the same stale token/route cannot succeed, and
  `ApiClient` already handled the one legitimate 401-retry-after-refresh
  transparently before a query ever sees the failure.
- **Zustand** owns state the frontend itself is the source of truth for
  across the session: the authenticated user/tokens (`src/store/auth-store.ts`)
  and the theme preference (`src/store/theme-store.ts`). Both use the
  `persist` middleware (`localStorage`) so a page refresh doesn't lose
  the session or the theme choice. `auth-store` additionally exposes
  `getAccessTokenValue()`/`resolveSession()` as plain functions (not
  hooks) for the two places that need the store outside a React render:
  `ApiClient`'s auth hooks and the router's root `beforeLoad`.

## 5. Theme system

`src/store/theme-store.ts` holds one persisted value, `mode: "light" |
"dark" | "system"`. `resolveTheme(mode)` turns that into an actual
`"light" | "dark"` (checking `prefers-color-scheme` when `mode ===
"system"`), and `applyTheme(mode)` toggles a `.dark` class on
`<html>` — Tailwind v4's `@custom-variant dark (&:where(.dark, .dark
*))` (`src/styles/globals.css`) drives every `dark:` utility off that
class, not off `prefers-color-scheme` directly, so `"system"` mode still
needs the class applied explicitly and re-applied on every OS-level
change. `src/app/theme-provider.tsx` does exactly that: applies the
theme on mount, and (only while `mode === "system"`) subscribes to
`matchMedia(...).addEventListener("change", ...)`, cleaning up on
unmount or mode change. `src/components/theme-toggle.tsx` is the only
UI control that calls `setMode`.

## 6. Routing

TanStack Router's file-based mode, `routesDirectory: "./src/pages"`,
`generatedRouteTree: "./src/app/routeTree.gen.ts"` (regenerated by the
Vite plugin on every dev/build run — never hand-edited, and excluded
from ESLint). `autoCodeSplitting: true` means every route's component is
already its own chunk with no separate `.lazy.tsx` files needed.

- `src/pages/__root.tsx` — the root route. Its `beforeLoad` calls
  `resolveSession()` once, before any child route's own `beforeLoad`
  runs — this is what lets every route guard downstream trust
  `useAuthStore.getState().status` is already settled
  (`"authenticated"`/`"unauthenticated"`), never still `"idle"`. Also
  supplies the router-level `notFoundComponent` (404) and
  `errorComponent` (uncaught render/loader errors).
- `src/pages/login.tsx` — the one public route. Its `beforeLoad` redirects
  to `/` if already authenticated (no reason to show the login form
  twice).
- `src/pages/_authenticated.tsx` — a pathless layout route (leading `_`
  removes the segment from the URL). Its `beforeLoad` redirects to
  `/login` if `status !== "authenticated"`; its `component` is
  `AppShell` (sidebar + top nav + footer + `<Outlet />`), so every nested
  route automatically gets that chrome for free.
- `src/pages/_authenticated/index.tsx` — the Health Dashboard, at `/`.

Adding a new protected page later means adding one file under
`src/pages/_authenticated/`; adding a new public page means one file
directly under `src/pages/`. Neither requires touching the router
instance (`src/app/router.tsx`) or the root route.

## 7. Application shell

`src/layouts/app-shell.tsx` composes `TopNav` + `Sidebar` + a routed
`<Outlet />` + `Footer`. The routed area is wrapped in both boundaries
this milestone requires:

- `src/components/error-boundary.tsx` — a class component (React still
  has no hook-based `componentDidCatch`), generic over its fallback so
  the same component serves the app shell's panel-level fallback and any
  future feature-level one.
- `src/components/loading-boundary.tsx` — a thin `<Suspense>` wrapper
  with a default spinner fallback, ready for the day a route/component
  actually suspends (none does yet — no feature lazily loads data via
  `Suspense` in this milestone).

The shell is responsive via Tailwind's default breakpoints (`Sidebar` is
`hidden` below `sm`); no custom breakpoint system was introduced.

## 8. WebSocket client

`src/services/websocket/ws-client.ts`'s `WebSocketClient` wraps the
native browser `WebSocket` (no library — same "don't add what isn't
approved" reasoning as the HTTP client). Per the backend protocol
(`docs/architecture/WEBSOCKET_FRAMEWORK.md`):

- The access token is passed as a `?token=` query parameter — the
  browser `WebSocket` constructor cannot set custom headers.
- Heartbeat is client-driven: a `setInterval` sends `{action: "ping"}`
  at `heartbeatIntervalMs` (default 30s); the server's `pong` is just
  another inbound message, not separately tracked.
- Reconnection uses exponential backoff, capped at `maxReconnectAttempts`
  (default 5), and is skipped entirely for a deliberate `disconnect()`.
- Active subscriptions are replayed after every reconnect
  (`resubscribeAll`) — the backend holds no subscription state across
  connections (Sprint 59 design), so the client must.

`src/hooks/use-websocket.ts` owns one `WebSocketClient` instance per
mount (via `useRef`), connecting on mount and disconnecting on unmount;
a second effect subscribes/unsubscribes to the caller's `eventTypes`
once connected. The Health Dashboard calls it with no event types — it
only needs the connection state, not a live event feed, in this
milestone.

## 9. Testing strategy

- **Vitest** (`vitest.config.ts` via `vite.config.ts`'s `test` block),
  `environment: "jsdom"`, `src/test/setup.ts` wires
  `@testing-library/jest-dom` matchers and starts/stops the shared MSW
  server around every test file.
- **MSW** (`src/test/msw/`) intercepts `fetch` at the network boundary —
  tests exercise the real `ApiClient`/hooks/store, never a mocked
  service module, so a contract drift between a hand-written mock and
  the real client's request-building logic can't hide a bug. `handlers.ts`
  covers the endpoints this milestone actually calls
  (`/auth/login`, `/auth/refresh`, `/auth/logout`, `/health`, `/ready`,
  `/version`); `fixtures.ts` builds response bodies shaped exactly like
  the real backend's envelopes.
- **React Testing Library** for component tests
  (`src/components/theme-toggle.test.tsx`,
  `src/features/auth/login-form.test.tsx`) — queries by role/label, the
  same way a user or a screen reader would, never by implementation
  detail (class names, internal state).
- **Hook tests** (`src/hooks/use-health.test.tsx`) render a tiny probe
  component through `src/test/test-utils.tsx`'s `renderWithQueryClient`
  (a fresh, retry-disabled `QueryClient` per test) rather than testing a
  hook in isolation outside React — closer to how the hook is actually
  used.
- **Store tests** (`src/store/auth-store.test.ts`) call the Zustand
  store's actions directly against MSW-mocked responses, including one
  `server.use(...)` override to exercise the refresh-failure path.
- **`WebSocketClient` unit tests** (`src/services/websocket/ws-client.test.ts`)
  stub the global `WebSocket` constructor with a small in-memory fake
  (`vi.stubGlobal`) rather than hitting a real socket — deterministic,
  and lets the reconnect/resubscribe path be tested under
  `vi.useFakeTimers()` without a multi-second real wait.

## 10. Known gaps (by design, not oversight)

- No production `.env` is committed; `VITE_API_BASE_URL`/`VITE_WS_BASE_URL`
  fall back to the local dev backend (`http://localhost:8000`) if unset —
  matching `docs/release/DEPLOYMENT_GUIDE.md`'s own default port.
- `Framer Motion` and `Recharts` are installed (required stack) but
  unused — no feature in this milestone animates anything or charts
  anything. They'll be exercised by the first feature milestone that
  needs them, not added speculatively here.
- The Health Dashboard is the only page. Every other domain
  (Watchlists, Portfolio, Screening, …) is out of scope for Milestone 1
  by the original brief ("no business features beyond basic health
  verification").
