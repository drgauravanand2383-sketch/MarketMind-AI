# MarketMind AI Frontend — Milestone 7: Real-Time Experience & Notification Center

Transforms the app from strictly request/response to event-aware, using
only the existing frozen WebSocket protocol (`/ws`, Sprint 59) and REST
API v1 — built on top of Milestones 1–6 (`docs/frontend/ARCHITECTURE.md`,
`MILESTONE_2.md` through `MILESTONE_6.md`, still the primary references
for the shell, auth, dashboard, and the established CRUD/optimistic-
update/testing conventions this milestone reuses). No backend code was
touched; every capability below wires up transport/UI that already
existed but was dormant.

## 1. Backend research, not backend changes

Zero backend changes — the WebSocket framework (`app/api/ws/`) and every
event it publishes were already complete and frozen. The frontend
already had a fully-built `WebSocketClient` (`services/websocket/
ws-client.ts`) and a thin binding hook (`hooks/use-websocket.ts`), but
**exactly one component — `ConnectivityPanel` — called it, purely for a
connection-status display**; nothing dispatched an inbound event
anywhere. This milestone's work was primarily wiring that dormant
capability up, after a full research pass directly against
`docs/architecture/WEBSOCKET_FRAMEWORK.md` and the real backend source
(not the doc's summary alone) to confirm two facts that shaped the whole
feature set:

- **`RISK_ASSESSMENT_COMPLETED` is a real, tested `EventType` that no
  REST router ever actually publishes** — confirmed via grep (zero
  callers of `EventPublisher.publish_risk_assessment_completed()`
  outside its own definition), matching that this milestone's own spec
  never lists it among the 7 events to consume. Modeled in
  `types/websocket.ts`'s `DomainEvent` union for exhaustiveness-checking
  completeness, but never subscribed to (§3) and never surfaced in the
  Notification Center.
- **Subscribing to an event type requires the exact same permission its
  REST equivalent already requires** (`app/api/ws/dependencies/
  permissions.py`) — a client without it gets a non-fatal
  `{type:"error",code:"forbidden"}`, and `event_types: []` ("subscribe
  to everything") would need broad permission across all 6 at once. The
  frontend therefore computes an explicit, permission-scoped subscribe
  list (§3) rather than ever sending an empty array.

Two architecture decisions were asked and approved by the user (both the
recommended option) before implementation:

1. **The spec's Activity Feed asks for "Research completed," but the
   backend has zero WebSocket event for research** (`EventType` has no
   research-related literal at all) — resolved as merging in entries
   from the existing Milestone 4 `session-activity-store.ts`
   (`recentResearch[]`) alongside the 6 real WS-driven event types,
   interleaved by timestamp. The Activity Feed is "this session's
   cross-domain activity," not a pure WebSocket event log.
2. **Whether the new persistent Notification Center should record every
   pre-existing `notify()` toast call site (~15 across Milestones 2-6:
   CRUD success/failure, form validation, etc.) or only the 6 real WS
   domain events** — resolved as the latter. The ~15 existing local
   toasts keep firing exactly as before; they are never written into
   `realtime-notification-store`.

## 2. Domain architecture

`types/websocket.ts`'s `EventDeliveryMessage`/`ServerMessage` no longer
carry an `unknown` payload — `DomainEvent` is a discriminated union
keyed by `event_type`, reusing every existing domain type field-for-
field (`Alert`, `BacktestRun`/`BacktestResult`, `RecommendationResult`,
`StrategyEvaluationResult`, `RiskAssessment`, `ExplainabilityResult`,
`ApplicationHealth`). `BACKTEST_STARTED` (payload: a synthetic `PENDING`
`BacktestRun`) and `BACKTEST_COMPLETED` (payload: the final
`BacktestResult`) share one backend `BacktestEvent` model but are
distinguished purely by the `event_type` string literal on the wire —
the same mechanism every other event type already uses, no
backend-specific handling needed.

## 3. The realtime dispatch pipeline

A new `useRealtimeSync()` hook (`hooks/use-realtime-sync.ts`) is the
**single mount point** for real-time behavior — mounted exactly once, in
`AppShell` (itself gated by `_authenticated.tsx`'s `beforeLoad`, so
mount/unmount already tracks login/logout for free). It owns the app's
one `useWebSocket()` call: `WebSocketClient.disconnect()` fires
unconditionally on that hook's unmount, so a second caller would tear
down the shared connection — `ConnectivityPanel` was changed from
calling `useWebSocket()` directly to reading a read-only Zustand mirror
(`store/realtime-connection-store.ts`) instead. This invariant is
documented on all three touch points and verified by grep (`grep -rn
"useWebSocket(" src` shows exactly one real call site).

`useRealtimeSubscriptions()` (`hooks/use-realtime-subscriptions.ts`)
computes the permission-scoped subscribe list, mirroring
`useVisibleFeatureItems` (`layouts/sidebar.tsx`) exactly — `HEALTH_
STATUS_CHANGED` is always included (auth alone is sufficient), the other
5 are gated by `alerts:read`/`backtest:read`/`portfolio:read`/
`strategy:read`/`explainability:read`, and `RISK_ASSESSMENT_COMPLETED`
is never requested.

On every inbound event, `useRealtimeSync` fans out to three pure,
independently unit-tested functions:

| Concern | Function | File |
|---|---|---|
| Cache invalidation | `invalidateForEvent(queryClient, event)` | `lib/realtime-invalidation.ts` |
| Notification Center entry | `toNotificationEntry(event)` | `lib/realtime-notifications.ts` |
| Toast | `toastFor(event)` (inline in `use-realtime-sync.ts`) | — |

All three use an exhaustive `switch` over `DomainEvent["event_type"]`
(with a `never`-typed `default`/return-`null` arm), so a future 9th
backend event type fails the build here until handled — required given
the project's strict-TS/no-`any` rule.

### Cache invalidation table

| Event type | Invalidates | Surgical? |
|---|---|---|
| `ALERT_GENERATED` | `alertsKeys.lists()` | domain-broad (payload carries no list params) |
| `BACKTEST_STARTED`/`COMPLETED` | `backtestingKeys.run(id)` + `.result(id)`, `id = payload.request_id` | surgical |
| `RECOMMENDATION_GENERATED` | `["portfolio","recommendations"]` prefix | domain-broad (`RecommendationResult` carries no `portfolio_id`) |
| `STRATEGY_EVALUATION_COMPLETED` | `strategyKeys.result(payload.request_id)` | surgical |
| `EXPLAINABILITY_COMPLETED` | `explainabilityKeys.result(payload.request_id)` | surgical |
| `HEALTH_STATUS_CHANGED` | `["system","health"]`, `["system","ready"]` | surgical (singleton) |
| `RISK_ASSESSMENT_COMPLETED` | no-op | never published |

Backtest/Strategy/Explainability events carry the exact id their query
hooks already key on, so invalidation is surgical; Alert/Recommendation
carry nothing more specific, so the whole domain-level prefix is
invalidated instead — still scoped to that one domain, never an
unrelated one ("refresh only impacted data," per the spec).

## 4. Notification Center

`store/realtime-notification-store.ts` follows the `session-activity-
store.ts`/`decision-history-store.ts` precedent exactly: a plain Zustand
store, no `persist` middleware, a capped array (200 entries — larger
than the 10/20 caps of the two prior session-only stores, since this is
meant to be a browsable log), explicit "session-only" docstring. There
is no durable history to back a real one — the WebSocket framework has
**zero message replay or persistence** (confirmed,
`docs/architecture/WEBSOCKET_FRAMEWORK.md` §6): a client that
(re)connects after an event fires simply never sees it.

Scoped to only the 6 real WS-driven domain events plus health status
changes (approved decision 2) — never the pre-existing non-WS toasts.
`unreadCount` is never stored, only derived, to avoid a second source of
truth; every consumer must select the stable `entries` array and
`.filter()` in the component body, never inside the Zustand selector —
documented directly on the store, since this is the exact
`useSyncExternalStore` "getSnapshot should be cached" infinite-loop
footgun M6 already hit and fixed 4 times (and which recurred twice more
during this milestone — see §11).

**Deep-linking is domain-limited by real backend constraints, not an
oversight**: `Alert`, `RecommendationResult`, and `StrategyEvaluationResult`
all carry no portfolio/watchlist id and have no standalone detail route
(both live only as tabs inside `/decisions/$portfolioId`) — entries for
those three domains render no link at all, rather than a misleading link
that always points at the same generic `/decisions` page. Only
`backtest` (`/historical-analysis/backtests/$runId`) and `explainability`
(`/historical-analysis/explainability/$requestId`) get a real deep link.

**Dropdown** (`components/notifications/notification-bell.tsx`, mounted
in `TopNav`): mirrors `UserMenu`'s open/close mechanics (pointerdown-
outside + Escape) but deliberately does not use `role="menu"`/
`role="menuitem"` — entries are read/navigate targets, not commands, so
the ARIA menu pattern's implied roving-tabindex arrow-key navigation
would be the wrong semantics. A plain labeled region instead.

**Full page** — `/notifications` (`pages/_authenticated/notifications/
index.tsx`, **no `requirePermission` guard**, unlike the 7 investment-
workflow domains: it reflects only the current user's own WebSocket
session, not a permission-gated resource). Client-side domain/read-
status/priority filters and free-text search — no backend endpoint
exists for this session-only data to filter server-side, the same
reasoned exception every other session-only list in this app (M4-M6)
already established. Grouped by date (Today/Yesterday/older). Clicking
an entry marks it read (and navigates, where a deep link exists).

**Nav entry**: a second hardcoded `SidebarLink` next to the existing
Dashboard one — not added to `FEATURE_NAV_ITEMS`, since it is not one of
the 7 permission-gated domains.

## 5. Live dashboard

`ConnectivityPanel` no longer calls `useWebSocket()` (§3) — it reads
`realtime-connection-store` and now shows a distinct badge per
`ConnectionState` (`CONNECTED`/`CONNECTING`/`RECONNECTING`/`FAILED`/
`DISCONNECTED` — `StatusBadge`'s `BadgeState` union grew 2 new literals),
"Last event"/"Last heartbeat" timestamps, and a manual **Reconnect**
button shown only in `"failed"`/`"disconnected"` states. An offline/
degraded banner (§7) sits above the badge grid.

`RecentActivity` no longer shows mock data (`recent-activity.mock.ts`
deleted entirely) — it merges `realtime-notification-store`'s entries
with `session-activity-store`'s research completions (approved decision
1), sorted newest-first, capped at 10, labeled "This session" rather
than the old "Demo data."

A new `RealtimeSummaryCards` component shows two session-scoped
WebSocket-event tallies — "N recommendations generated this session"
and "N alerts generated this session" — both a plain `.filter().length`
over `realtime-notification-store`'s already-collected entries. Neither
is a real backend aggregate: there is no "total recommendations"
endpoint at all (recommendations are generate-on-demand, never listed),
so the alert count is treated the same way for dashboard-wide
consistency rather than mixing a real `GET /alerts` total with a session
tally on the same page.

## 6. `ws-client.ts` reliability additions

- **Connect timeout** (`connectTimeoutMs`, default `10_000`): a timer
  started in `openSocket()`, cleared on both `onopen` and `onclose`; if
  it fires while still connecting/reconnecting, force-closes the socket,
  routing through the existing `onclose` → `scheduleReconnect` path.
- **`"failed"` terminal state**: `ConnectionState` grew a 5th literal.
  `scheduleReconnect()` sets it once `reconnectAttempts >=
  maxReconnectAttempts`, instead of silently giving up forever. A new
  public `reconnect()` resets the attempt counter and retries
  immediately — wired through `useWebSocket`'s return value into
  `realtime-connection-store`, and from there into `ConnectivityPanel`'s
  manual Reconnect button.

## 7. Offline/online detection

`store/network-status-store.ts` wires `navigator.onLine` +
`online`/`offline` window listeners once at module load (same pattern
`apiClient.setAuthHooks` in `providers.tsx` already uses). The 3 states
the spec asks for are a pure derivation of two already-tracked signals
(`lib/connectivity.ts`'s `deriveConnectivityLevel`), not a new combined
store:

1. **Offline** (`!online`) — wins regardless of WS state.
2. **Server/WS unreachable while online** — `wsState ∈
   {"reconnecting","failed","disconnected"}`.
3. **Degraded but reachable** — WS connected, but the already-polled
   `useHealth()` reports non-`HEALTHY`.

## 8. Toast system: `pinned`

`notification-store.ts`'s `durationMs: 0` already meant "never
auto-dismiss" — `pinned?: boolean` is a **clearer-named alias** for it,
not a second independent field (`pinned: true` simply forces the
zero-duration path). None of the ~15 pre-existing M2-M6 call sites pass
it, so they are entirely unaffected. Used for `CRITICAL`-priority
`ALERT_GENERATED` toasts and the WS `"failed"` terminal-state toast
(fired exactly once per transition into `"failed"`, via a `useRef`
guard in `useRealtimeSync`) — both "don't let this silently disappear"
cases.

## 9. Testing strategy

The 3 near-identical hand-rolled `FakeWebSocket` classes that existed
before this milestone (`test/routing.test.tsx`,
`features/dashboard/dashboard-page.test.tsx`,
`services/websocket/ws-client.test.ts`) were consolidated into one
shared `test/mock-websocket.ts` — the explicit project rule "every
component should be reusable where practical" applied to test
infrastructure too. It also adds `simulateMessage`/`simulateClose`/
`simulateError`, an `installFakeWebSocket()` setup helper, and
`buildDomainEvent`/`buildEventEnvelope`/`buildServerEventMessage` —
fully-typed envelope builders (`PayloadFor<EventType>` enforces the
right fixture per event type at compile time) reusing every existing
domain fixture (`buildAlert`, `buildBacktestResult`, etc.), plus 2 new
fixture builders (`buildRecommendationResult`,
`buildStrategyEvaluationResult`, `buildRiskAssessment`) added to
`fixtures.ts` for parity with the domains that only had a `test*` const
before.

**Coverage by area**: WS transport lifecycle including the new
connect-timeout/`"failed"`/`reconnect()` behavior (`ws-client.test.ts`),
the React binding including `lastEventAt`/`lastHeartbeatAt`
(`use-websocket.test.ts`), permission-scoped subscriptions
(`use-realtime-subscriptions.test.ts`), the full dispatch pipeline per
event type including the `RISK_ASSESSMENT_COMPLETED` no-op and the
`"failed"`-state pinned toast (`use-realtime-sync.test.ts`), the pure
invalidation/notification-mapping functions table-driven over all 8
`EventType`s (`realtime-invalidation.test.ts`,
`realtime-notifications.test.ts`), the notification store including a
regression test for the selector-loop footgun
(`realtime-notification-store.test.tsx`), offline/online detection
(`network-status-store.test.ts`), `pinned` (`notification-store.test.ts`),
the bell dropdown and full page including filtering/search/grouping/
mark-read/deep-linking (`notification-bell.test.tsx`,
`notification-center-page.test.tsx`), the enhanced connectivity panel
(`connectivity-panel.test.tsx`, didn't exist before this milestone), the
real merged activity feed (`recent-activity.test.tsx`, rewritten from
mock-data assertions), the two summary-tally cards
(`realtime-summary-cards.test.tsx`), and a new real-router test for
`/notifications` (`routing.test.tsx`) confirming it is reachable by any
authenticated user with no permission redirect, unlike every other
M2-M6 domain route. Accessibility follows the unchanged M1-M6
convention: every interaction driven through `getByRole`/`getByLabelText`.

**Two real bugs found and fixed by these tests, not just written
around**: `use-realtime-subscriptions.ts`'s own selector
(`state.user?.permissions ?? []`) allocated a fresh empty array on every
call whenever `user` was `null`, tripping the exact `useSyncExternalStore`
infinite-loop detector its own docstring warns about — caught by its own
test (`user: null`), fixed by hoisting a stable module-level
`NO_PERMISSIONS` constant. The **same pre-existing footgun was found
dormant in `layouts/sidebar.tsx`'s `useVisibleFeatureItems`** (present
since Milestone 2, never triggered because `Sidebar` only ever renders
post-authentication when `user` is non-null) and fixed identically as a
drive-by hardening, since it's the same one-line, zero-risk fix pattern
already established.

## 10. Known mocked/gap areas

- **`RISK_ASSESSMENT_COMPLETED` is real but never published** — no REST
  router calls `EventPublisher.publish_risk_assessment_completed()`
  (confirmed gap, `docs/architecture/WEBSOCKET_FRAMEWORK.md` §8).
  Modeled for type-exhaustiveness only; never subscribed to, never
  surfaced anywhere in the UI.
- **No message replay or persistence** — the Notification Center and
  Activity Feed are strictly "since this tab connected," never a durable
  history, the same session-only framing every prior milestone
  established for domains without a durable backend list.
- **Single-process backend** — `ConnectionManager` is in-memory,
  per-process; a user with two tabs against a load-balanced multi-
  instance deployment could see different events on each tab depending
  on which instance it landed on.
- **Alert/Recommendation/Strategy notifications cannot deep-link to a
  specific record** — their payloads carry no portfolio id, and neither
  domain has a standalone detail route.
- **Dashboard recommendation/alert counts are session WebSocket
  tallies, not real backend aggregates** — there is no "total
  recommendations" endpoint at all.
