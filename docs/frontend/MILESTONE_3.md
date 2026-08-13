# MarketMind AI Frontend — Milestone 3: Watchlists & Portfolio Management

Builds the first complete investment workflow — Watchlists → Portfolio
View — on top of Milestones 1–2 (`docs/frontend/ARCHITECTURE.md`,
`docs/frontend/MILESTONE_2.md`, still the primary references for the
shell, auth, and dashboard). No company research, screening,
recommendations, or backtesting UI exists yet — those permission-gated
routes remain the M2 `ComingSoon` placeholders.

## 1. Backend additions (both post-freeze, additive — see `docs/release/API_CONTRACT_V1.md` §1)

Two genuine gaps in the frozen API were found while building this
milestone, both resolved with the user's explicit approval before any
backend code was touched (the same pattern established in Milestone 1
for the auth router):

- **`PATCH /watchlists/{id}/companies/{ticker}/notes`** — `WatchlistService
  .update_notes()` existed since the service was first built but was
  never reachable over REST; `AddCompanyRequest.notes` could only be set
  once, at add-time. New endpoint, new request schema
  (`UpdateNotesRequest`), 6 new backend tests, zero existing behavior
  changed.
- **`name` filter on `GET /watchlists` / `GET /portfolio`** — every
  existing filter matches watchlist *contents* (sector/country/theme/
  ticker/company); none let you search by the watchlist's own name. The
  spec required a watchlist-name search box, and filtering client-side
  after the fact would have desynced the server's own pagination totals
  — a direct conflict with "reuse existing API pagination" and "do not
  compute anything on the frontend." Added as a case-insensitive
  substring match, mirroring the existing `company` filter's own
  convention exactly, just at the watchlist level instead of the item
  level.

Both were verified against the full backend suite (2795 tests) with
zero regressions before any frontend code consumed them.

**Deliberately not built**, per the actual contract (confirmed by
direct source inspection, not assumption): there is no "duplicate
watchlist" backend endpoint, and none was added — duplication is
composed entirely from two existing endpoints (§3). There is also no
recommendation-availability flag; availability is inferred from a `404`
on `GET /portfolio/recommendations` (§4), the same convention the
backend itself uses for `GET /portfolio/risk`.

## 2. Watchlist architecture

`src/types/watchlist.ts` and `src/types/portfolio.ts` mirror
`app.watchlist.models`, `app.risk.models`, `app.recommendations.models`,
and `app.agents.portfolio_intelligence.models` field-for-field, each
verified against the real backend source before being typed —
`sector`/`country`/`theme` are modeled as plain `string | null` (the
backend has no enum for any of them), while `RiskCategory`/
`RiskSeverity`/`RecommendationType` are modeled as string-literal unions
(they *are* closed Python `str` enums).

`src/services/api/watchlist-api.ts` / `portfolio-api.ts` follow the
established thin-wrapper convention exactly (M1's `system-api.ts`/
`auth-api.ts`): one function per endpoint, unwrap `.data`, no logic.
Two API-shape details worth calling out because they'd otherwise look
like bugs:

- `watchlistApi.delete` (watchlist) returns `Promise<void>` (`204`);
  `watchlistApi.removeCompany` returns `Promise<Watchlist>` (`200` +
  body) — the one documented DELETE/200 exception in the contract.
- `portfolioApi.getIntelligence` passes `skipRetry: true` explicitly. A
  `503` (no `ANTHROPIC_API_KEY` configured) is in `ApiClient`'s default
  retryable-status list — retrying it would add ~900ms of pointless
  backoff before ever surfacing what is actually a stable, non-transient
  fact about the deployment. This was caught by a test that timed out
  waiting for the "unavailable" state to appear (§8) — a real bug the
  test suite found, not a test written to match existing behavior.

## 3. CRUD, filtering, sorting, pagination

`src/features/watchlists/watchlist-list-page.tsx` composes: search +
collapsible filter panel (`watchlist-filters.tsx`), an adaptive table/
card list (`watchlist-table.tsx`), pagination
(`components/table/pagination.tsx`), and three dialogs (create, rename,
delete-confirm). All server-side: `WatchlistListParams` maps 1:1 onto
the backend's real query params (`page`, `page_size`, `sort`,
`direction`, `name`, `sector`, `country`, `theme`, `ticker`) — the
frontend never filters, sorts, or paginates a list it already has
client-side.

**Duplicate watchlist** — since no backend endpoint exists, `useDuplicateWatchlist`
composes two already-approved endpoints: `POST /watchlists` (new name,
`"{name} (copy)"`) then one `POST .../companies` call per source item.
Deliberately *not* optimistic (§6) — it's several sequential network
calls, not one reversible write.

**Notes editing** — `notes-cell.tsx`, a click-to-edit control (not a
full dialog; one field doesn't warrant one). Its label/textarea `id`
uses `useId()`, not a `notes-${ticker}` template string — the adaptive
company table (§5) mounts a desktop and mobile copy of every row
simultaneously, and a plain ticker-derived id would collide between the
two, breaking the label association for whichever copy isn't first in
the DOM (a real bug found and fixed during testing, §8).

## 4. Portfolio integration

There is no `Portfolio` domain model on the backend — `portfolio_id`
*is* a `watchlist_id`, and `GET /portfolio`/`GET /portfolio/{id}` return
the identical `Watchlist` shape as `/watchlists`. `src/hooks/use-portfolio.ts`
reflects this: `usePortfolioSummary`/`usePortfolioIntelligence` are
plain queries; `usePortfolioRisk`/`usePortfolioRecommendations` wrap
their query to expose `isUnavailable` (a `404` — "nothing generated
yet," a normal state) separately from `isError` (any other failure) —
callers render an `EmptyState` for the former, an `ErrorState` for the
latter. `usePortfolioIntelligence` additionally has to distinguish a
`503` (service not configured on this deployment) from a generic error,
since that's the one portfolio endpoint the backend can return
"unavailable" *without* a 404.

Per the spec ("no recommendations... UI yet"), `PortfolioRecommendationsPanel`
shows only availability + summary counts (strong-buy/buy/watch totals)
— never the candidate list, and `POST /portfolio/recommendations`
(generating new ones) is wrapped in the API module for completeness but
never called from any component.

## 5. Component reuse

New reusable primitives, all under `src/components/` (not scoped to
the watchlist feature, since none of them reference watchlist types):

- **`Badge`** — sector/country/theme labels get a stable color via a
  deterministic string hash into a fixed palette, since none of those
  fields are a closed enum with a natural color mapping.
- **`Dialog`** — focus-trapped, `Escape`-to-close, restores focus to
  the trigger on close; every M3 dialog (create/rename watchlist, add
  company, delete/remove confirmations) is built on this one component,
  not four bespoke modals.
- **`ConfirmDialog`** — built on `Dialog`, used for both watchlist
  delete and company remove.
- **`Panel`** — extracted *from* the Milestone 2 dashboard (was a
  private, unexported component there) into `src/components/panel.tsx`
  so the watchlist detail page's seven sections and the dashboard's
  panels share one implementation instead of two near-identical ones.
- **`SortableColumnHeader`**, **`Pagination`** — generic over any
  backend `sort`/`page` query-param pair.

## 6. State management

Unchanged split (TanStack Query = server state, Zustand = client state
— M1/M2's own instruction, repeated verbatim in this milestone's spec),
with one new store: `src/store/watchlist-ui-store.ts` holds the list
page's search/filter/sort/page/page-size selections — UI state that
*shapes* a query, never the query result itself. Not persisted:
reopening the app to a stale filter set would be surprising, not
helpful (same reasoning as M2's `mobileNavOpen`).

## 7. Optimistic update strategy

Rename, notes edits, watchlist delete, and company remove are all
optimistic; company *add* and duplicate are not (see below for why).
Every optimistic mutation in `src/hooks/use-watchlists.ts` follows the
same shape:

1. `onMutate`: cancel in-flight queries for the affected keys
   (`snapshotWatchlistCaches`) — so a slow real response can't land
   mid-optimistic-write and get silently clobbered by it — then
   snapshot the current cache state and apply the optimistic value via
   `patchWatchlistInCache`/`removeWatchlistFromCache`. Both write to
   *every* cache entry that could be showing the affected watchlist:
   the detail query and any currently-cached list page's row for it —
   a rename made from a list-row dialog is reflected in the list
   immediately, not just once a refetch happens.
2. `onError`: restore the exact snapshot (`rollbackWatchlistCaches`) and
   show a specific "...rolled back" toast. These mutations pass
   `meta: { suppressErrorToast: true }` so the global API-error toast
   (`src/app/query-client.ts`, M2) doesn't *also* fire a generic one for
   the same failure — one toast per error, not two.
3. `onSettled`: invalidate the detail query regardless of outcome, so
   the cache is eventually consistent with the server even if the
   optimistic write and the real response disagreed in some way this
   mutation didn't anticipate.

**Add company** and **duplicate** are not optimistic: add can fail with
a `409` (ticker already tracked) that depends on server-side state the
client can't fully predict client-side without re-deriving backend
validation logic, and duplicate is several sequential calls, not one
atomic write — there's no single "optimistic value" to show or roll
back.

## 8. Testing strategy — three real bugs found, not just written to spec

Same stack as M1/M2 (Vitest/RTL/MSW); `src/test/msw/watchlist-store.ts`
is a small stateful in-memory mock (create/list/get/rename/delete/
add-company/remove-company/update-notes, plus a `queryWatchlists` that
emulates the real filter/sort/pagination semantics) so tests exercise
genuine request→response round trips instead of one static fixture per
endpoint. `resetWatchlistStore()` runs in the global `afterEach` as a
safety net against cross-test leakage.

Three real product bugs surfaced *by* the test suite while wiring it up
— worth recording since a milestone report that only lists "tests
pass" undersells what the tests actually did:

1. **MSW handler-ordering bug** (test infra, but modeled on a real
   footgun): `/portfolio/:id` was registered before the literal
   `/portfolio/summary|intelligence|risk|recommendations` routes,
   so the wildcard shadowed all four — "summary" got treated as a
   portfolio id. Fixed by reordering, mirroring the *real* backend's
   own registration-order requirement for the same four routes
   (`app/api/v1/portfolio/router.py`).
2. **Duplicate DOM ids** in `NotesCell` (§3) — found because a test
   scoped to "the desktop table" still couldn't find a uniquely-labeled
   textarea; fixed with `useId()`.
3. **Missing `skipRetry` on `getIntelligence`** (§2) — found because a
   test asserting the "unavailable" empty-state appeared within 1s
   consistently timed out; the real cause was `ApiClient` retrying the
   503 twice with backoff first.

**Coverage by spec area**: CRUD flows + optimistic updates + rollback
(`use-watchlists.test.tsx`, hook-level via `renderHook`, and
`watchlist-list-page.test.tsx`/`watchlist-detail-page.test.tsx`,
component-level), filtering/sorting/pagination (list-page tests +
`watchlist-store.ts`'s own query emulation), notifications
(list-page's create-flow test, `NotificationCenter` mounted alongside),
accessibility basics (`aria-sort` on sortable headers, dialog
focus/labeling, table `scope`/`caption`, all asserted via RTL role
queries rather than a separate scanner), responsive/adaptive layout
(asserting both the `sm:table` and `sm:hidden` markup exist
simultaneously — same jsdom limitation noted in M1/M2: real CSS
breakpoint *rendering* isn't something a jsdom-based test can verify),
MSW-backed integration (every CRUD/portfolio test), and one real-router
test (`src/test/routing.test.tsx`) added for `/watchlists/$watchlistId`
specifically.

**A fourth bug, also found via the real-router test**: `_authenticated/
watchlists.tsx` + `_authenticated/watchlists.$watchlistId.tsx` (TanStack
Router's flat-file convention) makes the first an *implicit layout* for
the second — since the list page renders no `<Outlet />`, navigating to
`/watchlists/$id` silently rendered the list page's own full content
instead of the detail page, with only the breadcrumb showing the
correct destination. Fixed by moving both into a `_authenticated/
watchlists/` directory (`index.tsx` + `$watchlistId.tsx`), the sibling
convention already used for `_authenticated/index.tsx` — TanStack Router
docs call this out, but it's an easy trap to fall into by filename
similarity alone, and no amount of manual review caught it before the
test did.

## 9. Known mocked areas

None. Every panel on the watchlist detail page consumes a real backend
endpoint — no local/demo data anywhere in this milestone (contrast M2's
dashboard, which had two intentionally-mocked panels since their
backend endpoints don't exist yet).
