# MarketMind AI Frontend — Milestone 8: User Settings, Personalization & Workspace Customization

Lets users personalize how MarketMind AI looks and behaves — theme, density, dashboard layout, table/chart defaults,
notification behavior, and accessibility — without touching any investment feature, recommendation logic, or backend
API. Built on top of Milestones 1–7 (`docs/frontend/ARCHITECTURE.md`, `MILESTONE_2.md` through `MILESTONE_7.md`).
Unlike every prior milestone, this one required **no backend research at all** — the spec is explicit that
personalization is entirely client-side (`No backend persistence`, `Persist user preferences using Zustand
persistence`), so the research phase was a full pass over the existing frontend codebase instead: which stores
already persist, what the dashboard's current card composition is, and what precedents (chart preferences, table
page sizes) already existed from earlier milestones that this one needed to build on rather than duplicate.

## 1. Two approved architecture decisions

1. **Dashboard card reorder/resize with no new dependency.** No drag-and-drop or grid-layout library exists in the
   project (confirmed — `package.json` has only React/TanStack/Zustand/Recharts/Framer Motion/Zod), and the project's
   constitution forbids adding one without explicit approval. Resolved as plain Move up/down and a size-cycle button
   per card (`dashboard-card-frame.tsx`, `features/settings/tabs/dashboard-tab.tsx`) — zero new dependencies, fully
   keyboard-accessible by default, no approval-gated risk.
2. **Saved Views scoped to Milestone 8's own settings.** The spec's "Saved filter presets / table layouts / chart
   preferences" doesn't say which filters/tables it applies to, and the app's only pre-existing filter UIs live
   inside investment-domain screens (Screening, Alerts, Watchlists) from earlier milestones — which this milestone's
   own Purpose statement says to preserve untouched ("Do NOT introduce new investment features"). Resolved as
   self-contained: Saved Views manages named presets of dashboard layouts, global chart-preference defaults, and the
   Notification Center's own filters (Milestone 7's own page, not an investment feature) — zero changes to
   Screening/Alerts/Watchlist filter code.

## 2. Store architecture

One new persisted store per spec section, matching the spec's own section boundaries rather than one mega-store —
each maps 1:1 onto a "Reset one section" scope and a Workspace Settings tab:

| Store | Persists | Covers |
|---|---|---|
| `preferences-store.ts` | ✅ (`marketmind-preferences`) | Appearance (accent color, density, default landing page, timezone display, number format), Tables (default page size), Charts (default data-label visibility), Notifications (toast duration, default pinned, sound, desktop, categories), Accessibility (reduced motion, high contrast, larger text, focus highlight) |
| `dashboard-layout-store.ts` | ✅ (`marketmind-dashboard-layout`, `isCustomizing` excluded via `partialize`) | Card order, hidden cards, per-card size |
| `saved-views-store.ts` | ✅ (`marketmind-saved-views`) | Named presets (dashboard-layout / chart-defaults / notification-filter) |
| `notification-filter-store.ts` | ❌ (session-only, matches `realtime-notification-store.ts`'s own non-persistence) | The Notification Center page's own filter state, lifted out of local `useState` (Milestone 7) so it's a real, capturable Saved-View payload |

**Theme mode (`theme-store.ts`) and sidebar-collapsed state (`ui-store.ts`) are deliberately not duplicated** — both
already exist as their own persisted stores from earlier milestones. The Workspace Settings Appearance tab surfaces
them directly (`<ThemeToggle />`, a checkbox bound to `useUiStore`) rather than re-storing the same value twice.

## 3. Making preferences real, not just stored

A preference that's saved but never read anywhere is a UI lie. Three existing pieces of state from earlier
milestones were wired to read the new global defaults, each as a **seed at store-creation time**, not a live
subscription — the existing per-view override mechanism stays intact:

- `watchlist-ui-store.ts` / `alerts-ui-store.ts` / `screening-ui-store.ts`'s `pageSize` now reads
  `usePreferencesStore.getState().tables.defaultPageSize` instead of a hardcoded `20` literal.
- `decision-workspace-store.ts` / `historical-analysis-ui-store.ts`'s `chartPreferences.showDataLabels` now reads
  `usePreferencesStore.getState().charts.showDataLabels` instead of hardcoded `false`.
- `notification-store.ts`'s `notify()` reads `notifications.toastDurationMs`/`notifications.defaultPinned` as its
  fallback when a call site doesn't pass an explicit `durationMs`/`pinned` — none of the ~15+ existing call sites
  across Milestones 2-7 needed to change, since the defaults are unchanged (6000ms, not pinned) unless the user
  actually changes them.

**Deliberately not retrofitted**: 5 one-off `page_size: 100`/`50` literals used to populate pickers/dropdowns
(`create-backtest-form.tsx`, `strategy-evaluate-form.tsx`, `signals-panel.tsx`, `signal-definition-picker.tsx`,
`decision-center-landing-page.tsx`) — these aren't "tables" in the browsing sense, they're "fetch enough items to
populate a selector," a different concept; touching 5 already-shipped, already-tested call sites for no real
user-facing benefit was judged out of scope.

## 4. Dashboard Customization

`dashboard-card-registry.tsx` is the single source of truth for all 9 existing dashboard cards (`UserCard`,
`ConnectivityPanel`, `QuickNavCards`, `RealtimeSummaryCards`, 3 charts, `HealthPanel`, `RecentActivity`) — each a
`{id, label, panelTitle?, render}` entry. `DashboardPage` was rewritten from three separate hand-laid-out grid rows
into **one unified `grid-cols-4` grid**, rendering cards in `dashboard-layout-store.ts`'s `cardOrder`, skipping
`hiddenCards`, sized by `cardSizes` (`sm`/`md`/`lg` → `col-span-1`/`2`/`4`) — so any card can be reordered relative
to any other, not just within its original row. A "Customize dashboard" toggle reveals per-card Move up/down, a
size-cycle button, and Hide, via `DashboardCardFrame`; hidden cards move into a "Hidden cards" section with a Show
button. The same actions are also available as a compact list in Workspace Settings' Dashboard tab
(`dashboard-tab.tsx`) for users who prefer managing everything from one place — both surfaces read/write the same
store, so they never drift.

## 5. Saved Views

`saved-views-store.ts` captures a **point-in-time snapshot** of the relevant live store when `saveView(name, kind)`
is called — not a live binding. `applyView(id)` dispatches by `kind` back into the owning store
(`dashboard-layout-store.applyLayout`, `preferences-store.setShowDataLabels`,
`notification-filter-store.applySnapshot`). `restoreDefaultsFor(kind)` resets the live store to its factory default
without touching any saved view — distinct from applying a user's own saved view.

## 6. Import / Export

`lib/preferences-io.ts` bundles every user-configurable value — `theme-store`, `ui-store.sidebarCollapsed`, all 5
`preferences-store` sections, `dashboard-layout-store`, and `saved-views-store` — into one JSON document
(`buildPreferencesExport()`), downloaded via a plain `Blob` + `URL.createObjectURL` anchor (no server round trip, no
new dependency). Import validates with `zod` (already a project dependency) **before writing anything to any
store** — `preferencesExportSchema.safeParse()` runs first; only on success does `applyPreferencesExport()` run.
"Rollback on invalid import" is therefore satisfied by construction, not a separate undo step: an invalid or
malformed file is rejected with a readable error, and the app's current preferences are never touched.

## 7. Accessibility

- **Reduced motion**: wraps the whole app in Framer Motion's own `MotionConfig` (`app/preferences-provider.tsx`) —
  every existing `motion.*`/`AnimatePresence` usage (`Dialog`, `NotificationCenter`, `Sidebar`'s mobile drawer,
  `ConfirmDialog`) already respects it automatically, with zero changes to any of those components. The same
  underlying field (`accessibility.reducedMotion`) is also the Appearance tab's "Enable animations" toggle,
  inverse-framed — one canonical field, not two that could drift out of sync.
- **High contrast / larger text / focus highlight**: classes toggled on `<html>` (`compact`/`large-text` scale the
  root font size, which proportionally scales nearly every rem-based Tailwind spacing/sizing utility in the app at
  once, rather than needing per-component changes; `high-contrast` applies a CSS `contrast()` filter over the whole
  page; `focus-highlight` strengthens the global `:focus-visible` outline) — the exact `documentElement.classList`
  pattern `theme-store.ts`'s `applyTheme` already established for dark mode, defined in `styles/globals.css`.
- **Density** (Appearance, not Accessibility, but the identical root-font-size technique) uses the same mechanism in
  the opposite direction.

## 8. Notification Preferences

Desktop notifications are genuinely permission-aware, not just a stored boolean: toggling it on in
`notifications-tab.tsx` calls the real `Notification.requestPermission()` browser API (only when permission is
still `"default"`) and only sets `desktopNotificationsEnabled: true` if the browser actually granted it.
`use-realtime-sync.ts` (Milestone 7's dispatch hook) now fires a real `new Notification(...)` for events that pass
both the enabled-categories filter and a live `Notification.permission === "granted"` check (permission can be
revoked from outside the app at any time). Toast duration/pinned defaults and the 6-domain category filter
(`enabledCategories`) also gate the Notification Center entry and toast — cache invalidation always runs regardless
(a data-freshness concern, not a noise preference).

## 9. Profile page

Read-only account/session/API information (`/profile`, no permission guard — available to any authenticated user,
same reasoning `/notifications` established in Milestone 7). **Never displays a raw token value** — only
`AccessToken`/`RefreshToken` metadata (`issued_at`/`expires_at`), since showing the actual secret on a "read-only
summary" page would be a real security regression. "Connected API" reads `API_BASE_URL`/`WS_BASE_URL`
(`services/api/config.ts`) plus `useVersion()` (already existed since Milestone 2).

## 10. Navigation

`/profile` and `/settings` are surfaced from `UserMenu`'s dropdown ("View profile" / "Workspace settings"), not the
sidebar — both are account-level pages, not one of the 7 permission-gated investment-workflow domains or a
cross-cutting tool like Notifications, so the account menu (the conventional home for this kind of page) was judged
the better fit over further crowding the sidebar.

## 11. Testing strategy

New test files per store/component, matching the established per-file granularity: `preferences-store.test.ts`,
`dashboard-layout-store.test.ts`, `saved-views-store.test.ts`, `notification-filter-store.test.ts`,
`preferences-io.test.ts` (export shape, round-trip, and 3 distinct invalid-import/rollback cases),
`preferences-provider.test.tsx` (accessibility class toggling), `profile-page.test.tsx` (including an explicit
assertion that raw token values never render), `workspace-settings-page.test.tsx` (tab switching, a control per tab,
saved-view save/apply, import validation-failure messaging, reset-all requiring confirmation), extended
`dashboard-page.test.tsx` (Customize-mode hide/show/resize interactions), extended `use-realtime-sync.test.ts`
(category-filter suppression, desktop notification firing/non-firing), and 2 new real-router tests (`/profile`,
`/settings`) in `routing.test.tsx` confirming both are reachable by any authenticated user with no permission
redirect.

**One real regression found and fixed by these tests, not written around**: lifting the Notification Center page's
filter state from local `useState` (Milestone 7) into a module-level Zustand store (§2, so it's a capturable Saved
View) meant the filter state now **persists across tests within the same file** instead of resetting on remount —
`notification-center-page.test.tsx`'s existing tests started failing because an earlier test's filter changes leaked
into later ones. Fixed by adding `useNotificationFilterStore.getState().resetFilters()` to that file's `beforeEach`,
the same reset-store-state-per-test convention every other test in this app already follows.

**Responsive layouts**: verified the same way every prior milestone did — Tailwind's `sm:`/`lg:` breakpoint
utilities throughout (the dashboard grid, tab lists, settings field rows) plus manual dev-server checks; this app
has no dedicated viewport-resize test infrastructure, and Milestone 8 didn't introduce one.

## 12. Known limitations

- **Timezone display and number format formatting are scoped to Milestone 8's own surfaces** (currently the Profile
  page, via `lib/formatting.ts`) — not retroactively applied to every date/number rendered across Milestones 2-7.
  Any future surface can adopt `formatNumber`/`formatDateTime` directly.
- **"Default table page size" only seeds 3 existing UI stores' initial value** (Watchlists, Screening, Alerts) — the
  5 one-off picker-population `page_size` literals elsewhere are unrelated ("fetch enough to populate a dropdown,"
  not "browse a table") and were left untouched, per §3.
- **"Sound on/off" is a stored UI preference only** — no audio file or Web Audio playback exists, exactly as the
  spec's own "(UI only)" annotation specifies.
- **Saved Views cannot capture Screening/Alerts/Watchlist filters** — by the approved scope decision (§1); only
  dashboard layouts, global chart defaults, and the Notification Center's own filters are saveable.
- **High contrast is a CSS filter, not a WCAG-audited alternate theme** — a real, working frontend-only effect, but
  not a substitute for a professionally designed high-contrast palette.
