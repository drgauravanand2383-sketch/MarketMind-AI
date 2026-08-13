# MarketMind AI Frontend — Milestone 9: Production Quality, Accessibility & Performance

Brings the frontend to production quality — accessibility, responsiveness, and runtime performance — without
introducing new business functionality (`docs/frontend/ARCHITECTURE.md`, `MILESTONE_2.md` through `MILESTONE_8.md`).
Unlike every prior milestone, this one is an audit-and-fix pass across the entire existing 8-milestone app rather
than a new feature domain: broad in scope (10 concern categories), not deep in any one area. Research was 3 parallel
background audits (accessibility; performance; mobile/error-recovery/consistency), each required to cite real
file:line evidence rather than generic advice, and to confirm categories that were already well-handled instead of
manufacturing findings. One question was asked and approved (recommended option): the "Search" keyboard shortcut
focuses the current page's own existing search input rather than a new global command-palette overlay, since the
Purpose statement explicitly rules out new business functionality and no global search exists anywhere in the app.

## 1. Accessibility

- **Keyboard-reachable tablists.** `DecisionWorkspaceTabs` and `WorkspaceSettingsPage` both implemented roving
  `tabIndex={isActive ? 0 : -1}` with no `ArrowLeft`/`ArrowRight`/`Home`/`End` handler at all — since inactive tabs
  carry `tabIndex={-1}`, a keyboard-only user could not reach any tab except whichever was already active (the most
  severe finding across all 3 audits). Fixed with a new shared `useRovingTablist` hook
  (`hooks/use-roving-tablist.ts`) — both tablists now share one implementation instead of two hand-rolled copies.
- **A real Tab-trap for `Sidebar`'s mobile drawer.** The drawer declared `role="dialog" aria-modal="true"` with
  correct initial-focus/return-focus/Escape handling (mirroring `Dialog`'s mechanics) but no actual Tab-key trap.
  `Dialog`'s existing, working trap was extracted into a new shared `useFocusTrap` hook
  (`hooks/use-focus-trap.ts`); both `Dialog` and `Sidebar` now use it instead of the drawer growing a second,
  duplicated implementation.
- **`UserMenu` no longer claims ARIA menu semantics it doesn't implement.** `role="menu"`/`role="menuitem"` imply a
  roving-tabindex arrow-key/Home/End keyboard model that was never built — the same reasoning
  `NotificationBell` (Milestone 7) already used to deliberately avoid that pattern. `UserMenu` now matches: a plain
  labeled region (`aria-label="User menu"`) of normal focusable links/buttons, `aria-haspopup="dialog"`.
- **Live-region announcements** added for state that previously updated silently: `NotificationBell`'s unread count
  (a visually-hidden `aria-live="polite"` span), `ConnectivityPanel`'s WebSocket connection state, and
  `RealtimeSummaryCards`' live session tallies.
- **Chart `aria-label`s.** Recharts' `accessibilityLayer` (default `true` since v3) already gives every chart's root
  SVG `role="application"`/`tabIndex={0}` and forwards any `aria-label` — 10 of 13 chart components already passed
  one explicitly; the 3 dashboard charts missing it (`ApiLatencyChart`, `HealthSummaryChart`,
  `ServiceAvailabilityChart`) now do too.
- **Heading-hierarchy fix.** `RecentActivity` rendered its own internal `<h3>` instead of taking a `panelTitle` from
  `dashboard-card-registry.tsx`, so outside customize mode its heading sat directly under the page's `<h1>` with no
  `<h2>` in between (every other card was correctly nested). The registry entry now supplies `panelTitle: "Recent
  activity"`; the component's own `<h3>` was removed (the "This session" label stayed, repositioned).
- **Semantic nav list.** `Sidebar`'s `SidebarNav` wrapped `<Link>`s directly in `<nav>` with no `<ul>/<li>`
  structure, unlike every other list in the app (`NotificationBell`, the dashboard's hidden-cards list) — fixed to
  match.
- **Color contrast**, computed via the WCAG relative-luminance formula, not eyeballed:
  - `dark:text-brand-500` (the dominant in-app link/text color, ~20 files) measured 4.05:1 against `slate-950`,
    failing the 4.5:1 AA threshold for normal text. A new `--color-brand-400` token (`oklch(0.71 0.17 260)`,
    verified 7.59:1 against `slate-950`) replaces it everywhere `dark:text-brand-500` was used for real text/links —
    **not** the separately-verified-fine `dark:bg-brand-500/10` badge backgrounds, which are untouched.
  - A reversed `text-slate-400 dark:text-slate-500` pattern (8 files) measured 2.57:1 in light mode, a clear AA
    failure — the app's dominant, correct convention is the opposite order (`text-slate-500 dark:text-slate-400`,
    used 240+ times elsewhere). All 8 were swapped to match.
- **What was already fine, confirmed rather than assumed**: zero `<div onClick>` anti-pattern anywhere in the
  codebase; `<main>`/`<nav aria-label>` landmarks correctly used; no component suppresses the browser's native focus
  ring (repo-wide grep for `outline-none`/custom `focus:ring` returned zero matches); every sampled page has exactly
  one `<h1>`.

## 2. Performance

- **Lazy-loaded Recharts.** All 13 Recharts-consuming components across 7 consumer files (`dashboard-card-registry`
  via a new `charts/lazy-dashboard-charts.tsx`, `backtest-detail-page`, `performance-attribution-panel`,
  `signals-panel`, `strategy-panel`, `risk-panel`, `recommendations-panel`) now use `React.lazy` + `Suspense`
  (`Skeleton` fallback) instead of static imports. Before: the shared Recharts core was baked into the single
  largest eager chunk (371.40 kB raw / 106.78 kB gzip), loaded on nearly every session because the dashboard (the
  default post-login landing page) statically imported 3 chart components. After: Recharts' core (`CategoricalChart-
  *.js`, ~90 kB gzip) is its own dynamically-loaded chunk, fetched only when a chart actually renders — this also
  gives the app's existing `LoadingBoundary`/`Suspense` infrastructure (mounted since Milestone 2, previously inert
  since nothing else in the app code-splits) its first real trigger.
- **Memoization** added where a merge/sort/filter ran unmemoized on every render: `RecentActivity`'s
  notification+research merge, `RunHistoryList`/`HistoricalAnalysisHistoryList`'s entry filters,
  `StrategyComparisonTable`'s score-sort. All operate on small, session-bounded arrays, so the fix is correctness-
  of-pattern rather than a measurable win — but the pattern itself is now consistent everywhere it applies.
- **`CompanyTable`'s double-render fixed.** It rendered *both* a desktop `<table>` and a mobile `<ul>` card list
  unconditionally, one hidden via `hidden ... sm:table`/`sm:hidden` CSS classes — doubling DOM node count for the
  same `Watchlist.items` data regardless of viewport, the one table in the app not provably bounded to a small row
  count (fetched unpaginated via `GET /watchlists/{id}`). A new shared `useMediaQuery` hook
  (`hooks/use-media-query.ts`, the same `window.matchMedia` + `addEventListener("change", ...)` pattern
  `theme-store.ts`/`theme-provider.tsx` already established) now picks exactly one representation to render.
  jsdom has no `window.matchMedia` at all — the hook falls back to `true` ("desktop") when unsupported, so existing
  tests that query `role="table"` keep working without every test needing its own stub.
- **Confirmed not applicable, not "fixed"**: image optimization (zero `<img>`/raster-asset usage anywhere — the app
  is entirely icon/emoji-based); virtualization (every list/table is bounded by server pagination, manual-entry
  practicality, or a small config-driven enumeration, except `CompanyTable`, addressed above by picking one layout
  rather than true virtualization — no new dependency needed); route-level code splitting (TanStack Router's
  `autoCodeSplitting: true`, `vite.config.ts`, already produces genuine per-route chunks from plain static route-file
  imports — confirmed via real build output, ~80 separate chunks — this was already working, not a gap).
- **A performance-audit claim independently verified and corrected, not acted on as given**: the audit stated
  `preferences-store.ts` imports `lib/preferences-io.ts`, which imports `zod`, explaining why Zod's chunk is
  unconditionally modulepreloaded. Grepping `preferences-store.ts`'s actual imports shows this is false — it only
  imports `zustand`/`zustand/middleware` and type-only imports; the dependency direction is the reverse
  (`preferences-io.ts` imports *from* `preferences-store.ts`). The real cause: `features/auth/login-form.tsx`
  directly imports `zodResolver`/`z` for its own login-form validation schema — a legitimate, unavoidable need since
  `/login` is the first page any unauthenticated visitor reaches, not a fixable "leak." No code change was made for
  this finding; it's recorded here so the (incorrect) original claim isn't repeated in a future pass.

## 3. Mobile

- **3 unprefixed multi-column grids** that squeezed on a 375px viewport now use `grid-cols-1 ... sm:grid-cols-N`:
  `add-company-dialog.tsx` (inside the 448px-capped `Dialog`), `performance-attribution-panel.tsx`,
  `recommendation-detail-panel.tsx`'s score tiles.
- **Touch targets** bumped on several icon-only/secondary controls that were well under the ~44px guideline:
  the sidebar collapse toggle and `NotificationBell` trigger (`p-2` → `p-2.5`), `DashboardCardFrame`'s 4 customize
  controls, `ThemeToggle`'s segmented buttons, `filter-row.tsx`'s move/remove buttons. Dense, opt-in toolbars
  (customize-mode controls, the segmented theme control) got a moderate increase rather than a forced 44px, which
  would not fit multiple controls in the available space — judged the right trade-off for a packed, non-primary
  control cluster.
- **`TopNav` reviewed at 375px.** Its actual composition (hamburger + wordmark + notification bell + 3-segment
  labeled theme toggle + user menu) is genuinely tight, and the touch-target increases above made it marginally
  tighter. A content-preserving spacing tightening was applied (`gap-3` → `gap-2 sm:gap-3`, `px-4` → `px-3 sm:px-4`
  on both flex groups and the header itself). Restructuring which elements collapse/hide on the smallest viewport
  (e.g. an icon-only theme toggle, or hiding the wordmark) would be a product/branding decision outside the
  Implementation Engineer's mandate — deferred, see §7.
- **Confirmed already fine**: `Dialog`'s `max-w-md` never overflows 375px; filter bars are consistently `flex
  flex-wrap`; no `h-screen`/hardcoded pixel heights exist anywhere (only `min-h-screen` floors).

## 4. Error recovery

- **Retry UX** swapped from bare error text / `EmptyState` (which has no retry affordance) to `ErrorState` (with a
  working `onRetry`) in 8 files for genuinely-error conditions: `signals-panel.tsx`, `strategy-panel.tsx`,
  `evaluate-alerts-panel.tsx` (mutations — retry re-invokes `.mutate(mutation.variables)`),
  `explainability-compare-page.tsx`, `research-compare-page.tsx` (queries — retry calls `.refetch()`), and
  `health-summary-chart.tsx`/`service-availability-chart.tsx` (which previously swallowed the actual error message
  behind a generic "Chart unavailable" string).
- **Site-wide offline/degraded-connectivity banner.** The offline/unreachable/degraded indicator previously only
  existed inside `ConnectivityPanel`, a dashboard-only card — a user on any other page while offline got zero
  indication. A new `ConnectivityBanner` (reusing the same `deriveConnectivityLevel`/`connectivityMessage` derivation
  from `lib/connectivity.ts`) is now mounted once in `AppShell`, above the routed `<Outlet />`, visible from every
  page. `ConnectivityPanel` is unchanged and still shows the same message as its own detailed status view — a
  lightweight global banner plus a detailed panel is the intended pairing, not a redundancy to remove.
- **Reactive session expiry.** `auth-store.ts`'s `sessionExpired` flag previously only got acted on by
  `_authenticated.tsx`'s `beforeLoad` guard, i.e. on the *next* navigation — a user mid-task got no feedback until
  they happened to navigate somewhere. A new `useSessionExpiryRedirect` hook, mounted in `AppShell`, reacts to the
  flag the instant it flips true and navigates to `/unauthorized` immediately. `beforeLoad`'s own check remains as a
  fallback for the case where the flag is already set before `AppShell` (and this hook) ever mounts — a hard page
  load whose initial `resolveSession()` refresh fails before routing occurs.
- **Per-card dashboard error isolation.** Only one `ErrorBoundary` existed app-wide (`AppShell`, wrapping the entire
  routed `<Outlet />`); `DashboardCardFrame` called `card.render()` directly with no boundary of its own, so one
  broken dashboard card took down the *entire* dashboard page. Each card's `render()` is now wrapped in its own
  `ErrorBoundary`, with an `ErrorState` fallback (retry resets just that card).
- **Confirmed already fine, not touched**: `ApiClient.request`'s silent refresh-and-retry on a 401; unexpected/
  malformed API failures already produce coherent `ApiError` messages via `parseResponse`/`safeJsonParse`.

## 5. Design consistency — a shared `Button`

No shared `Button` component existed anywhere — every button was a one-off Tailwind string, and "primary" buttons
alone had drifted to 4+ unrelated size/padding combos (`px-3 py-2 text-sm`, `px-3 py-1.5 text-sm`, `px-3 py-1.5
text-xs`, `px-2 py-1 text-xs`) with no apparent tiering. A new `components/button.tsx` establishes exactly 2 sizes
(`sm`/`md`, `md` matching `LoadingButton`'s existing default exactly so the two line up when used together) and 5
variants — `primary`/`secondary`/`destructive`/`destructive-ghost`/`destructive-outline`. The app's 3-way destructive
split (solid for modal confirm-destroy, ghost for inline row-remove, outlined for one standalone dangerous action)
was judged **intentional tiering by context, not drift** — kept as 3 distinct variants rather than collapsed into
one. `LoadingButton` (a distinct isLoading/spinner concern) is untouched.

**Deliberately not a retrofit of every button in the app** (~20+ files use the old inline pattern) — applied to new
Milestone 9 code and the highest-leverage existing call sites: `ConfirmDialog` (used by every delete-confirmation
flow app-wide, so this one file's adoption reaches the most screens), `ResetAllButton`,
`WatchlistListPage`'s "Create watchlist", `SavedViewsPanel`'s "Save current as…". The remaining call sites are a
known, accepted gap — see §7.

## 6. Keyboard shortcuts

A new `shortcuts-store.ts` (persisted, `marketmind-shortcuts`) holds a user-configurable `Record<ShortcutAction,
string>` keybinding for 8 actions: `search` (default `/`), `help` (`?`), and 6 navigation actions —
Dashboard (`d`), Watchlists (`w`), Decision Center (`c`), Historical Analysis (`h`), Notifications (`n`), Settings
(`s`). A single global `useKeyboardShortcuts` hook (mounted once in `AppShell`) listens for `keydown` on `document`:
shortcuts never fire while a modifier key is held or focus is inside an editable element (input/textarea/select/
contenteditable), so normal typing is never hijacked. Navigation to a permission-gated domain
(Watchlists/Decision Center/Historical Analysis) is a silent no-op for a user who lacks that permission, mirroring
`Sidebar`'s own `useVisibleFeatureItems` gating — a shortcut never navigates someone into an immediate `/forbidden`
redirect.

"Search" focuses the current page's own existing search input, tagged `data-shortcut-target="search"` on all 6
search inputs in the app (Watchlists, Screening results, Screening landing, Notification Center, backtest periods,
Decision Center recommendations) — the approved decision (see intro) over building a new global search feature.
"Help" (`?`) opens a `ShortcutsHelpDialog` cheatsheet listing every action and its current key. Rebinding happens in
a new "Shortcuts" tab in Workspace Settings (`features/settings/tabs/shortcuts-tab.tsx`) — click "Change," press any
key (Escape cancels), or "Reset"/"Reset all shortcuts" to restore defaults. Binding collisions are not prevented
(if two actions share a key, the first-defined action wins, deterministically) — judged acceptable for a v1 rather
than adding collision-detection UI for an edge case a user would have to deliberately create.

## 7. Known limitations

- **The performance audit's Zod/preferences-store causal claim was wrong** — see §2. Documented here so it isn't
  repeated as fact in a future pass.
- **`Button` is not retrofitted across the whole app** — adopted in `ConfirmDialog`, `ResetAllButton`,
  `WatchlistListPage`, `SavedViewsPanel` only. ~20 other files still use the pre-Milestone-9 inline Tailwind pattern
  for primary/secondary buttons.
- **No accessible data-table fallback for any of the 13 charts.** Recharts' `accessibilityLayer` gives per-point
  keyboard/tooltip narration, not an at-a-glance textual summary — building a full tabular fallback for all 13 charts
  was judged out of scope for this pass.
- **`TopNav`'s mobile layout got spacing tightening only**, not a structural redesign (icon-only theme toggle,
  hiding the wordmark, etc.) — those are product/branding calls outside the Implementation Engineer's mandate; see
  §3.
- **Keyboard shortcut binding collisions are not prevented** — see §6.
- **Sidebar's own `transition-[width]` desktop-collapse animation** (plain CSS, not Framer Motion) is a real,
  layout-reflow-triggering cost, reviewed and accepted as a largely irreducible cost of a genuine width-collapse
  interaction, not force-fixed via an awkward transform-based redesign.

## 8. Testing

New/extended test files, one per changed unit, matching the established per-file granularity: `use-focus-trap`
and `use-roving-tablist` are covered through their real consumers (`dialog.tsx`'s existing behavior tests,
`sidebar.test.tsx`'s new Tab-trap test, `decision-workspace-page.test.tsx`'s and `workspace-settings-page.test.tsx`'s
new arrow-key navigation tests) rather than duplicated in isolated hook tests. New: `user-menu.test.tsx` (had zero
prior coverage; now covers the ARIA-semantics change directly), `company-table.test.tsx` (desktop vs. mobile layout
branches, stubbing `window.matchMedia` since jsdom has none), `connectivity-banner.test.tsx`, `dashboard-card-
frame.test.tsx` (error isolation), `button.test.tsx`, `shortcuts-store.test.ts`, `shortcuts-tab.test.tsx`, and a new
`describe` block in `routing.test.tsx` covering the reactive session-expiry redirect and 5 keyboard-shortcut
scenarios (navigation, permission-gating, editable-target-ignoring, search-focus, help-dialog) against the real
router. A stale test-file comment describing the old "renders both layouts simultaneously" `CompanyTable` behavior
(`watchlist-detail-page.test.tsx`) was corrected to describe the new single-layout behavior.

**This machine showed repeated transient flakiness under heavy parallel test load throughout this milestone** —
timeouts and vitest worker-pool startup failures that were not reproducible when the same test(s) ran in isolation
or in a smaller batch. Every apparent failure during this milestone was rerun in isolation before being treated as
real; all were confirmed as environmental flakiness, not code regressions, except the one real regression below.

**One real regression found and fixed**: lazy-loading `HistoricalTimeline` (§2) meant its content — including a
specific note about session-only recommendation markers — no longer renders synchronously.
`backtest-detail-page.test.tsx`'s existing assertion on that text was a `screen.getByText`; changed to `await
screen.findByText(..., {}, { timeout: 3000 })` to await the `Suspense` boundary's resolution.

## 9. Verification

`npx tsc --noEmit -p .` clean; full-repo `npx eslint . --max-warnings 0` clean; `npx vite build` succeeds
(confirmed the Recharts core split into its own dynamically-loaded chunk, no longer part of the eager entry graph);
targeted and full `npx vitest run` passes (modulo the documented transient infrastructure flakiness above, always
confirmed via isolated rerun).
