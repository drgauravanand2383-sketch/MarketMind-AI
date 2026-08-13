# MarketMind AI Frontend — Milestone 2: Authentication Experience & Dashboard

Builds the first complete end-to-end experience — Authentication →
Dashboard — on top of Milestone 1's shell
(`docs/frontend/ARCHITECTURE.md`, still the primary reference for
folder structure, the API client, and the WebSocket client; this
document only covers what M2 added or changed). No investment
workflows (watchlists, screening, recommendations, …) are implemented
here — each has a placeholder route only.

## 1. Authentication flow

### 1.1 Session lifecycle states

`useAuthStore.status` is one of `"idle" | "authenticated" | "unauthenticated"`.
`"idle"` only exists between store creation and the root route's
`beforeLoad` resolving it — no route component ever renders while it's
still `"idle"` (`src/pages/__root.tsx`'s `pendingComponent` covers that
window if session resolution is slow).

### 1.2 Login

`src/features/auth/login-form.tsx`: React Hook Form + Zod
(`username`, `password`, `rememberMe`), built from the reusable
`FormField`/`LoadingButton` primitives (§4). On success, navigates to
`redirectTo` (see §1.4).

### 1.3 Remember me (client-side only)

There is no backend concept of "remember me" — both a remembered and a
non-remembered login get the identical token pair. What differs is
**where** the session is persisted:

- Checked (default): `localStorage` — survives closing the browser.
- Unchecked: `sessionStorage` — gone the moment the tab closes.

Implemented in `src/store/auth-store.ts` via a custom Zustand `persist`
`storage` that reads a small `marketmind-remember-me` flag (always in
`localStorage`, since it has to be readable before we know which of the
other two stores to consult) and delegates to `localStorage` or
`sessionStorage` accordingly. Switching the flag also proactively clears
the *other* storage's stale copy.

### 1.4 Protected routes, redirect-with-return

- `src/pages/_authenticated.tsx`'s `beforeLoad` is the single guard for
  every authenticated route (nested routes inherit it automatically —
  TanStack Router runs a parent's `beforeLoad` before any child's).
  Not authenticated → redirect to `/login`, carrying
  `search: { redirect: location.href }`.
- `src/pages/login.tsx` reads that `redirect` search param
  (`redirectSearchSchema`, `src/lib/route-search.ts`) and navigates
  there instead of `/` after a successful login. Already-authenticated
  visitors to `/login` are bounced straight to `/`.

### 1.5 Session loading

The root route's `beforeLoad` (`resolveSession()`) runs before any
child route, so every guard downstream sees a settled status. Its
`pendingComponent` (a full-screen spinner) only appears if that
resolution is slow — normally instant for a synchronous rehydration
check, occasionally visible if it has to make a live refresh call.

### 1.6 Expired session vs. never signed in

`useAuthStore.sessionExpired` is set **only** when an *existing*
session's silent refresh fails (`refresh()`'s catch branch, and only if
`status` was `"authenticated"` going in) — never for "never logged in"
and never by `logout()`. `_authenticated.tsx`'s guard checks this flag:
set → redirect to `/unauthorized` (an explanatory interstitial, "your
session has ended, sign in again") instead of straight to `/login`. This
only fires on the *next* navigation attempt after the session actually
expires — there is no background timer forcibly ejecting an idle,
already-rendered authenticated view mid-session; that's consistent with
how most SPAs handle this and avoids surprising a user who's mid-task.

### 1.7 Unauthorized vs. forbidden

Two distinct interstitials, both built on the shared `StatusPage`
component (§4):

- `/unauthorized` (401-flavored): session problems — see §1.6.
- `/forbidden` (403-flavored): authenticated, but lacking a specific
  permission. `src/lib/permissions.ts`'s `requirePermission(permission)`
  is a reusable `beforeLoad` guard factory; every one of the 7 domain
  placeholder routes (`src/pages/_authenticated/{watchlists,research,
  screening,recommendations,backtesting,explainability,risk}.tsx`) uses
  it with the *real* backend permission string for that domain (from
  `docs/release/API_CONTRACT_V1.md`'s `RequirePermission` catalog —
  `watchlist:read`, `research:read`, `screening:read`, `portfolio:read`
  ×2 for Recommendations/Risk, `backtest:read`, `explainability:read`).
  This is a UX convenience only — `hasPermission`/`useHasPermission`
  read the client's own copy of `user.permissions`; the backend enforces
  every permission independently on every request regardless of what
  the frontend renders.

### 1.8 Logout

`src/layouts/user-menu.tsx`'s logout button calls the `useLogout`
mutation, then navigates to `/login` on success (the store clearing
itself doesn't trigger a route re-guard on its own — there's no pending
navigation to intercept — so the UI explicitly sends the user there).

### 1.9 JWT refresh

Unchanged from Milestone 1: `ApiClient`'s 401 handling
(`src/services/api/client.ts`) calls the configured `onUnauthorized`
hook, wired to `useAuthStore.getState().refresh` in
`src/app/providers.tsx`, with one retry-after-refresh per request and
concurrent-401 coalescing.

## 2. Dashboard architecture

`src/features/dashboard/` composes into `dashboard-page.tsx`:

| Panel | Data source |
|---|---|
| `user-card.tsx` | `useCurrentUser()` (client state) |
| `connectivity-panel.tsx` | `useHealth`/`useReadiness`/`useVersion`/`useWebSocket` (real) |
| `health-panel.tsx` | `useHealth` (real) |
| `quick-nav-cards.tsx` | `FEATURE_NAV_ITEMS` filtered by the user's real permissions |
| `recent-activity.tsx` | **local static mock data** — see §6 |
| `charts/health-summary-chart.tsx` | derived from real `GET /health` (component-state counts) |
| `charts/service-availability-chart.tsx` | derived from real `GET /health` (per-service state → 100/50/0 score) |
| `charts/api-latency-chart.tsx` | **local static mock data** — see §6 |

Every data-backed panel follows the same three-state pattern:
`isPending` → `Skeleton`/`SkeletonList`; `isError` → `ErrorState` with a
`Retry` button wired to `refetch()`; success → the real content. This is
the same reusable trio every other panel in the app uses (§3).

## 3. Reusable states, notifications, and forms

- **Loading/empty/error** (`src/components/states/`): `Skeleton`/
  `SkeletonList`, `EmptyState`, `ErrorState` (message + optional
  `onRetry`), and `StatusPage` (full-page code/title/description/action —
  backs 404, `/unauthorized`, `/forbidden`, and the root error boundary,
  so there's one interstitial component, not four).
- **Notifications** (`src/store/notification-store.ts` +
  `src/components/notifications/notification-center.tsx`): a small
  ephemeral (never persisted) Zustand store — `notify(type, message,
  options)`/`dismiss(id)` — rendered as a fixed toast stack
  (Framer Motion enter/exit, `role="alert"`/`aria-live="assertive"` for
  error/warning, `role="status"`/`aria-live="polite"` for info/success).
  Identical `{type, message}` pairs reuse the existing toast instead of
  stacking duplicates — relevant for a health-check poll that keeps
  failing every 15s. **Integrated with API errors** at the `QueryClient`
  level (`src/app/query-client.ts`'s `QueryCache`/`MutationCache`
  `onError`): any `ApiError` a query/mutation surfaces becomes a toast
  automatically, except `401` (already handled by the silent-refresh +
  session-expiry redirect in §1.6 — a generic toast on top would be
  redundant/confusing).
- **Forms** (`src/components/forms/`): `FormField` (label + input with
  `aria-invalid`/`aria-describedby` wired to the error message —
  spreads directly onto `{...register("field")}`) and `LoadingButton`
  (`aria-busy`, disables itself, swaps in `loadingText` while pending).
  `LoginForm` (§1.2) is the first consumer; both are intentionally
  generic enough for any future form.

## 4. Layout

- **Sidebar** (`src/layouts/sidebar.tsx`): collapsible (icon-only)
  desktop rail, persisted via `useUiStore.sidebarCollapsed`
  (`src/store/ui-store.ts`, `persist`); a separate off-canvas drawer for
  small screens (Framer Motion slide-in, backdrop click / `Escape` /
  clicking a link all close it, focus moves to the close button on open
  and back to the trigger on close). Both list Dashboard plus whichever
  of the 7 domains the signed-in user has permission for.
- **Top nav**: mobile hamburger (opens the drawer via
  `useUiStore.setMobileNavOpen`), theme switcher, user menu.
- **User menu** (`src/layouts/user-menu.tsx`): avatar-initials trigger,
  `role="menu"`, closes on outside click or `Escape` (focus returns to
  the trigger), contains the logout action.
- **Breadcrumbs** (`src/layouts/breadcrumbs.tsx`): derived purely from
  the current pathname via `FEATURE_NAV_ITEMS` (falls back to a
  title-cased segment) — a new domain route needs no separate
  breadcrumb config.
- **Sidebar preference persistence**: only `sidebarCollapsed` is
  persisted (`partialize`); `mobileNavOpen` is intentionally transient —
  reopening the app with yesterday's mobile drawer left open would be a
  bug, not a feature.

## 5. State management

Unchanged split from Milestone 1 (TanStack Query = server state,
Zustand = client state), with two additions:

- `src/store/notification-store.ts` — ephemeral, never persisted (§3).
- `src/store/ui-store.ts` — `sidebarCollapsed` persisted,
  `mobileNavOpen` not (§4).

Persisted stores as of M2: theme (`theme-store.ts`), auth session
(`auth-store.ts`, with the remember-me storage split from §1.3), and
sidebar preference (`ui-store.ts`).

## 6. Known mocked areas

Two panels are placeholders, per the milestone's own scope ("No
investment workflows... yet") and its explicit instruction to mock
what has no backend endpoint yet, rather than inventing one:

- **Recent activity** (`src/features/dashboard/recent-activity.mock.ts`):
  static local data, not a network call to an endpoint the backend
  doesn't have. Swap this module for a real `useQuery` once a backend
  activity-feed endpoint exists — every other panel already shows that
  exact pattern to follow.
- **API response times** (`src/features/dashboard/charts/api-latency-chart.mock.ts`):
  same reasoning — the backend doesn't track/expose response-time
  history. Both are visibly labeled "Demo data" in the UI, never
  presented as if they were live.

The other two charts (component-health summary, per-service
availability) are **not** mocked — both are derived from the real
`GET /health` response already powering the health panel.

The 7 domain routes themselves are placeholders (`ComingSoon`, built on
`EmptyState`) — permission-gated and reachable, but with no real feature
behind them yet, exactly as scoped.

## 7. Accessibility

- Every interactive control has an accessible name (`aria-label` where
  there's no visible text — hamburger, sidebar collapse toggle, drawer
  close, notification dismiss).
- Focus management: the mobile drawer moves focus to its close button on
  open and restores it to whatever was focused before on close; the user
  menu does the same around `Escape`.
- Keyboard: mobile drawer and user menu both close on `Escape`; every
  interactive element is a real `<button>`/`<a>`, so native keyboard
  operability (Tab/Enter/Space) needs no extra wiring.
- Live regions: toasts use `role="alert"`/`aria-live="assertive"` for
  error/warning, `role="status"`/`aria-live="polite"` for info/success;
  form errors are linked to their input via `aria-describedby` and flip
  `aria-invalid`.
- Contrast: entirely Tailwind's default slate/brand palette at the
  weights Milestone 1 already established (no new ad-hoc colors
  introduced), which are AA-contrast by construction at the shades used
  (600+ for text on white, 100/200 for text on slate-900/950).
- Not independently verified: no automated contrast/axe-style scanner
  was added (would be a new, unapproved test dependency) — the above is
  verified by construction (semantic HTML, ARIA attributes present and
  tested — §8) and manual reasoning about the existing palette, not a
  tool-driven audit.

## 8. Testing strategy

Same stack as Milestone 1 (Vitest, React Testing Library, MSW); one
config change and one new pattern:

- **`vite.config.ts`**: Vitest's `pool` is set to `"threads"`. The
  default `forks` pool intermittently timed out spawning a worker
  process on this machine (a different test file failed to start each
  run — a pool-startup flake, not a test bug); `threads` runs workers
  in-process instead and has been reliable and 3-4x faster since.
- **`src/test/setup.ts`** stubs `window.scrollTo` (jsdom doesn't
  implement it; TanStack Router calls it for scroll restoration on every
  successful navigation).
- **New: real-router integration tests** (`src/test/routing.test.tsx`).
  Unlike component tests that mock `@tanstack/react-router`'s `Link`,
  this file builds an actual `createRouter({ routeTree, history:
  createMemoryHistory(...) })` and asserts on real `beforeLoad` guard
  behavior end to end — unauthenticated → `/login`, expired session →
  `/unauthorized`, missing permission → `/forbidden`, and successful
  render of the destination route. One non-obvious requirement:
  `await router.load()` must be called explicitly before rendering —
  with a real browser `History`, the initial `popstate` subscription
  triggers the first match resolution, but `MemoryHistory` starts with
  its one entry already in place, so no history "change" event ever
  fires and the router is left in `status: "pending"` with empty
  `matches` forever otherwise (only discovered because two tests that
  asserted on rendered *content*, not just the resolved pathname, hung).
- **Coverage by spec area**: authentication flow + session
  restore/expiry (`auth-store.test.ts`), protected routing
  (`routing.test.tsx`), permission guards (`permissions.test.ts`),
  dashboard rendering (`dashboard-page.test.tsx`), notifications
  (`notification-store.test.ts`, `notification-center.test.tsx`), forms
  (`form-field.test.tsx`, `loading-button.test.tsx`,
  `login-form.test.tsx`), loading/error states (`error-state.test.tsx`),
  mobile navigation/responsive behavior (`sidebar.test.tsx` — the
  *interactive* behavior of the drawer; jsdom has no layout engine, so
  actual CSS-breakpoint rendering itself is not something a jsdom-based
  test can verify, same limitation noted in Milestone 1).
