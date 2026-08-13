# MarketMind AI Frontend — Milestone 4: Company Research & Screening

Builds the Company Research and Screening workflows on top of
Milestones 1–3 (`docs/frontend/ARCHITECTURE.md`, `MILESTONE_2.md`,
`MILESTONE_3.md`, still the primary references for the shell, auth,
dashboard, and the established CRUD/optimistic-update/testing
conventions this milestone reuses rather than reinvents). No
recommendations, strategy evaluation, risk analysis, or backtesting UI
exists yet — those permission-gated routes remain the M2 `ComingSoon`
placeholders.

## 1. Backend additions (both post-freeze, additive — see `docs/release/API_CONTRACT_V1.md` §1)

Two genuine gaps were found while researching the actual backend
surface before writing any frontend code (the same "confirm against
real source, ask before adding" pattern established in M1's auth router
and M3's notes-editing endpoint), both approved by the user before any
backend code was touched:

- **`POST /screening/profiles/{profile_id}/duplicate`** —
  `ScreeningEngine.duplicate_profile()` existed since the engine was
  first built but was never reachable over REST. New endpoint, new
  request schema (`DuplicateScreeningProfileRequest`), wraps the one
  existing method — no new logic.
- **`name` filter on `GET /screening/profiles`** — mirrors the M3
  watchlist `name` filter exactly, for the identical reason: the spec
  needed a way to search saved profiles by name, and the endpoint had
  sort/pagination but no name filter.

Both were verified against the full backend suite (2800 tests) with
zero regressions before any frontend code consumed them.

**Deliberately not built**, per explicit user decision after the actual
backend surface was researched (not assumed):

- **Company Research reports and Screening run results have no durable,
  cross-session history.** Both are cached only in a thin,
  `InMemoryResultStore` at the HTTP layer — in-process, cleared on
  restart, no list endpoint (`docs/architecture/INTELLIGENCE_API.md`
  §2). Building real persistence for either would be new backend
  business logic, explicitly out of this milestone's scope ("Do not
  modify backend APIs or business logic" beyond the two additive items
  above). The "recent research" / "recent screening runs" sections of
  the spec are instead a **session-only, client-side-only** list
  (§6) — labeled "this session" in the UI, never implying a durable
  history the backend doesn't have.
- **No company search/autocomplete endpoint exists anywhere** in the
  real API surface. Company entry for both research and screening is
  plain free text (`company_name`/`ticker` fields), never a lookup.
- **No WebSocket events exist for research or screening.** Both
  `POST /research/company` and `POST /screening/run` are synchronous
  request/response only — the full `EventType` enum has no research/
  screening member. "Research progress indicator" is therefore a
  client-side indeterminate loading state (the mutation's own
  `isPending`, an `aria-live="polite"` status line, and the toast fired
  from `onMutate`), never a real multi-step progress bar.

## 2. Domain architecture

`src/types/research.ts` and `src/types/screening.ts` mirror
`app.agents.company_research.models` and `app.screening.models`
field-for-field, verified against the real backend source (not
assumed) before being typed. Two shapes are easy to get wrong by
assumption and are called out in the type files' own docstrings:

- There is **no single `sector`/`country`/`confidence` field** on a
  research report's company overview — only derived, evidence-weighted
  lists (`sector_analysis`, `country_exposure`, both `weight: int` —
  a raw mention count, not a 0–1 fraction) and a nested
  `confidence_summary.overall_confidence`. The UI renders these as
  proportional bars (`weighted-exposure-list.tsx`) labeled with the raw
  count, never inventing a normalized percentage the backend doesn't
  provide.
- `CompanyMetrics` (screening) is a **closed set of ~30 fields**
  (`extra="forbid"` on the backend model) with names that don't always
  match what a first guess would produce — `pb_ratio`/`ps_ratio`/
  `ev_ebitda`, not `price_to_book`/`price_to_sales`/`ev_to_ebitda`; no
  `volume`/`52-week` fields exist at all. `src/features/screening/
  screenable-fields.ts` is the single source of truth for this list —
  the field selector, value-type coercion, and the "run screening"
  company-entry form all read from it, so a mismatch would fail to
  compile rather than silently drift.

`src/services/api/research-api.ts` / `screening-api.ts` follow the
established thin-wrapper convention exactly. `narrative: null` on a
research report means "no LLM call was made" (an unmatched company),
rendered as an explicit empty state, never as an error or a missing
field.

## 3. Company Research

`src/features/research/`: a landing page (free-text entry form +
session-recent list), a batch page (dynamic company rows via
`useFieldArray`), and a result page covering every field the spec
requires — company overview, sector/country/theme exposure, narrative
(or its explicit empty state), supporting evidence, latest news,
relationships, data-quality notes (`key_risks` — deliberately labeled
"Data quality notes," never "risk," since the backend's own docstring
is explicit these are coverage limitations of the report, not a
market/investment risk assessment), generated timestamp, and a disabled
"Export (coming soon)" placeholder button per the spec.

## 4. Screening

`src/features/screening/`: a landing page (server-side name search +
sort + pagination, mirroring the M3 watchlist list page exactly),
profile CRUD (create/rename/duplicate/delete, all reusing
`Dialog`/`FormField`/`LoadingButton`), and the builder
(`builder/screening-builder.tsx`):

- **Field/operator/value editors** — field choices come from
  `screenable-fields.ts` (§2); the value editor's shape is dictated
  entirely by the selected operator (`value-editor.tsx`): a `[low,
  high]` pair for BETWEEN, a comma-separated list for IN/NOT_IN, a
  plain scalar otherwise — mirroring `ScreenFilter`'s own backend
  `model_validator` exactly.
- **AND/OR groups** — `group-list.tsx` manages `LogicalGroup`s (id,
  logic, optional `parent_group`); a filter's group assignment is a
  dropdown of existing groups. Cycle prevention
  (`group-utils.ts#wouldCreateCycle`) mirrors the backend's own
  `_detect_group_cycle` (`app/screening/models.py`) and is applied
  *before* a cyclic parent ever becomes selectable, not just validated
  after the fact.
- **Enable/disable, reorder** — a per-filter checkbox and up/down
  buttons (`▲`/`▼`), deliberately not drag-and-drop — keyboard-
  accessible by default, no new dependency.
- **Validation** (`validate-draft.ts`) mirrors the backend's own
  `model_validator`s client-side (BETWEEN bounds, non-empty IN/NOT_IN,
  a value present for every other operator, cycle-free groups) so a
  save fails fast in the UI instead of round-tripping to a 422; the
  backend remains the actual source of truth.

**Run screening** (`run-screening-panel.tsx`): since there's no company
search backend, entry is manual — but scoped down to only the metric
fields the profile's own filters actually reference (derived from
`profile.filters`, not all ~30 `CompanyMetrics` fields), which is both
more usable and all `ScreeningEngine.evaluate_companies()` would read
regardless.

**Screening results** (`screening-results-table.tsx`): matched/failed
companies, score, matched/failed filter lists — all read directly off
`ScreenResult`/`FilterEvaluation`, no client computation. Sort, filter
(by match status), search, and pagination are the one deliberate,
reasoned exception to "no frontend computation": `POST /screening/run`
and `GET /screening/results/{id}` both return the full, unpaginated
results array in one call, with no server-side page/sort/filter params
to defer to — unlike watchlists or screening profiles, where a server
equivalent exists and is used instead.

## 5. Comparison

`research-compare-page.tsx` / `screening-compare-page.tsx` — pure
presentation over already-fetched data, no new metric computed:

- **Research**: exactly two selected reports (`useComparisonStore` caps
  it at 2), a field-by-field table with a row highlighted whenever the
  two values differ.
- **Screening**: up to four selected runs, a per-ticker matrix (rows =
  the union of every ticker across the selected runs, columns = the
  selected runs) showing each run's own `passed` boolean per ticker —
  a row is highlighted only when the runs' own booleans disagree for
  that ticker, and a ticker not screened in a given run shows "Not
  screened" rather than a fabricated status.

## 6. State management

Unchanged split (TanStack Query = server state, Zustand = client
state), with three new stores:

- **`session-activity-store.ts`** — the session's own research/
  screening-run activity. Deliberately **not persisted** to
  `localStorage`: a reload starting empty, rather than implying
  durability the backend doesn't provide, was the explicit product
  decision behind §1's "session-only" resolution.
- **`comparison-store.ts`** — which report/result ids are selected for
  comparison; a newest-selection-bumps-oldest cap (2 for research, 4
  for screening), never silently refusing further picks.
- **`screening-ui-store.ts`** — the profile list's name-search/sort/
  page selections, the same scope and non-persistence reasoning as M3's
  `watchlist-ui-store.ts`.

## 7. Optimistic updates

Screening profile **rename** (via the generic `useUpdateScreeningProfile`,
which also serves the builder's own save), **duplicate**, and **delete**
are all optimistic, following the exact `onMutate`/`onError`/`onSettled`
shape M3 established in `use-watchlists.ts`. Duplicate is the one new
wrinkle: unlike rename/delete, which patch an *existing* cache entry,
duplicate has no existing detail entry to write into — it synthesizes a
temporary profile (`optimistic-${uuid}`) from the source profile plus
the new name, inserts it at the top of every cached list page, then
swaps it for the server's real object on success or removes it and
restores the exact snapshot on failure.

## 8. Notifications

Reuses the M2 notification system exactly. Research: "Researching…"
(`onMutate`) and "Research complete…" (`onSuccess`, distinguishing a
matched vs. unmatched company in the message). Screening: "Screen
created," "Profile updated," "Profile deleted," plus the same
rolled-back-specific toasts M3 established for optimistic failures.
API errors are automatic and required no per-domain wiring — the
global `QueryCache`/`MutationCache` `onError` handlers in
`src/app/query-client.ts` already cover every query/mutation
app-wide; the three optimistic screening mutations pass
`meta: { suppressErrorToast: true }` to avoid double-toasting against
their own specific rollback message, the same convention as M3.

## 9. Navigation

`/research` and `/screening` converted from M2's `ComingSoon`
placeholders into real routes, using the directory + `index.tsx`
sibling convention M3's real-router test caught a bug over
(`_authenticated/research/index.tsx` + `batch.tsx` + `$requestId.tsx`
+ `compare.tsx`, and `_authenticated/screening/index.tsx` +
`$profileId.tsx` + `compare.tsx` + `results/$resultId.tsx` — never a
flat `research.tsx` + `research.$id.tsx`). The sidebar and dashboard
quick-nav needed no changes: both already read `FEATURE_NAV_ITEMS`
(M2), which already listed `/research` and `/screening`.
`layouts/breadcrumbs.tsx` gained four more per-route label resolvers
(research report, screening profile, screening result — each a cache
hit against the same query the page itself uses), following the exact
pattern M3 established for the watchlist detail crumb.

## 10. Testing strategy

Same stack as M1–M3 (Vitest/RTL/MSW). New MSW test infrastructure:

- **`test/msw/result-store.ts`** — a generic id→value cache mirroring
  the real backend's `InMemoryResultStore` semantics, instantiated once
  each for research reports and screening run results.
- **`test/msw/screening-store.ts`** — a stateful profile CRUD/search/
  sort/pagination mock, the screening equivalent of M3's
  `watchlist-store.ts`, including the Milestone 4 `name` filter and
  duplicate endpoint.
- **`test/msw/screening-evaluator.ts`** — a minimal mock evaluator
  supporting all 9 `ScreenOperator`s, used by the `/screening/run`
  handler so tests exercise genuine pass/fail request→response round
  trips (mirroring the real backend test suite's own `AAPL: true,
  TINY: false` pattern) instead of one canned fixture.

**One pre-existing test fixed, not written to spec**:
`test/routing.test.tsx`'s "renders the requested domain page" test
previously asserted `/research` was still a `ComingSoon` placeholder
(true as of M3, false as of this milestone) — repointed at `/risk`,
which remains one, so the test still asserts the general
permission-gated-placeholder-route mechanism rather than a fact this
milestone made false.

**Coverage by spec area**: research workflow and screening workflow
(landing/batch/result pages, builder, run panel, results table — all
MSW-backed integration tests), profile CRUD + optimistic updates +
rollback (`use-screening.test.tsx`, hook-level, and
`screening-landing-page.test.tsx`, component-level, mirroring M3's
`use-watchlists.test.tsx` split exactly), builder validation as pure
unit tests (`validate-draft.test.ts`, `group-utils.test.ts` — cheaper
and more exhaustive than driving every combination through the DOM),
filtering/sorting/pagination (`screening-results-page.test.tsx`,
client-side per §4's reasoned exception), comparison (both compare
pages, including the differing-row/cell highlight), notifications
(`NotificationCenter` mounted alongside the relevant workflow tests),
accessibility basics (every interaction driven through `getByRole`/
`getByLabelText`, which fails outright if a label or role is missing —
the same convention M1–M3 used; no separate accessibility-scanner
dependency was introduced), session-store behavior
(`session-activity-store.test.ts`, `comparison-store.test.ts`), and
three additional real-router tests (`/research`, `/screening`,
`/screening/$profileId`) alongside M3's existing
`/watchlists/$watchlistId` one.

## 11. Known mocked/gap areas

- **Research/screening "recent" history is session-only, not durable**
  (§1, §6) — by explicit product decision, not an oversight.
- **No company search/autocomplete anywhere** (§1) — free-text entry
  only, for both research and screening company entry.
- **"Research progress indicator" is an indeterminate loading state**,
  not a real multi-step progress bar (§1) — no WebSocket events exist
  for either domain to drive one.
- **Export is an inert placeholder button** on the research result
  page, per the spec's explicit "export placeholder" requirement — no
  export functionality exists yet.
- **AND/OR group nesting is a flat-dropdown UI**, not a visual drag-and-
  drop tree — the underlying data model supports arbitrary nesting
  (§4), but the builder's UI presents it as "assign this filter to one
  of these existing groups" plus "set this group's parent to one of
  these existing groups," not a rendered tree diagram.
