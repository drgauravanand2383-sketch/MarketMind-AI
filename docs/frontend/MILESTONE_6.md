# MarketMind AI Frontend — Milestone 6: Historical Analysis Center

Builds the Historical Analysis Center — Backtesting, Explainability, and
Performance Attribution presented as one coherent analytical workflow —
on top of Milestones 1–5 (`docs/frontend/ARCHITECTURE.md`,
`MILESTONE_2.md` through `MILESTONE_5.md`, still the primary references
for the shell, auth, dashboard, and the established CRUD/optimistic-
update/testing conventions this milestone reuses, especially M5's
`decision-history-store.ts` and comparison-mode pattern). Live alerts /
a notification center are explicitly out of scope, per the milestone
spec. This is the final planned domain milestone — after this, every
one of the 7 original Milestone 2 nav domains has a real page; none
remain a `ComingSoon` placeholder.

## 1. Backend research, not backend changes

Like Milestone 5, this required **zero backend changes** — every
endpoint the spec needed already existed (`app/backtesting`,
`app/explainability`). The work was a full research pass against the
real source to nail down field-for-field shapes and surface genuine
capability gaps before writing any frontend code. Two backend facts
reshaped the whole feature set:

- **"Performance Attribution" is not a separate domain** — it's the
  optional `performance_attribution` field on `ExplainabilityResult`
  (`app/explainability/models.py`'s own module docstring: "Explainability
  **& Performance Attribution** Engine"). One `POST /explainability`
  call, gated by three optional ids (`strategy_evaluation_id`/
  `risk_assessment_id`/`backtest_run_id`), unlocks the strategy/risk/
  attribution sections of one result — not four separate request modes.
- **Backtesting and Explainability are both durably persisted** via
  real repositories (`BaseBacktestRepository`/`BaseExplainabilityRepository`)
  — unlike Research/Screening-results/Signals, which use the ephemeral
  `InMemoryResultStore` M4/M5 documented. A 404 on either domain means
  the id genuinely doesn't exist, not "the backend restarted" — both
  detail pages show a plain `ErrorState`, not the "no longer available"
  empty state M4/M5 established for the in-memory domains.

Three architectural questions were resolved with the user before
implementation, all approved as recommended:

1. **No backend endpoint lists/searches existing
   `RecommendationResult`/`StrategyEvaluationResult`/`RiskAssessment`
   ids** to build a `HistoricalSnapshot` from — resolved as **build from
   session history**: the Backtesting snapshot-builder and the
   Explainability generate form both source their id dropdowns from
   this session's own Decision Center activity, reusing (and extending)
   M5's `decision-history-store.ts` rather than inventing a parallel
   store.
2. **Timeline "recommendation markers" have no backend traceability** —
   `BacktestPeriod` carries no back-reference to the `HistoricalSnapshot`
   that produced it, and no GET endpoint ever returns the original
   snapshot list. Resolved as **track client-side at creation time**: a
   new `backtest-markers-store.ts` captures the mapping the frontend
   itself submits at `POST /backtests` time, keyed by the resulting
   `run_id`. This only works for backtests created in the current
   session — a run loaded by id from an earlier session (or after a
   reload) renders the timeline without markers, explained in the UI
   rather than silently.
3. **"Timeline attribution" doesn't exist** — `PerformanceAttribution
   .period` is a single label for the whole backtest, not a per-period
   series. Resolved as a **single-snapshot attribution panel** anchored
   to one backtest run's date range, not an evolving chart.

## 2. Domain architecture

`src/types/backtesting.ts` and `explainability.ts` are new, mirroring
`app.backtesting.models` and `app.explainability.models` field-for-
field. Two easy-to-get-wrong shapes worth calling out:

- **Every return/drawdown/win-rate value is a plain percentage number**
  (`12.34` means 12.34%), never a 0–1 fraction — confirmed against
  `app/backtesting/engine.py`'s own arithmetic, and copied verbatim
  (same scale) into `PerformanceAttribution`.
- **`HistoricalSnapshot.benchmark_value` is the one value nothing in
  the pipeline can derive** — accepted as directly caller-supplied, the
  same resolution `CandidateEvidence.planning_score` (M5) used for an
  analogous gap. `BacktestPeriod.portfolio_value` is a deterministic
  *proxy* derived only from already-computed 0–100 component scores,
  never a real valuation or live market data.

## 3. Backtesting

`features/historical-analysis/backtesting/`: a create form (name,
description, date range with a `start ≤ end` refinement, initial
capital, benchmark ticker, replay mode, optional strategy checkboxes
from `useStrategiesList`) embedding a snapshot builder (§1) — a table
of rows, each picking a recommendation/strategy/risk result from
session history plus a timestamp and optional benchmark value. A
backtest can be submitted with zero snapshots; it simply produces zero
periods (an explicit, documented backend behavior, not a frontend
guard). `POST /backtests` creates the request and runs it fully
synchronously (`app/backtesting/engine.py` — no background execution),
returning the aggregate `BacktestResult` directly; `isPending` is the
loading indicator, the same convention every prior milestone's
synchronous generate/evaluate endpoint established.

The detail page (`backtest-detail-page.tsx`) shows 8 summary-metric
cards (portfolio/benchmark/excess return, max drawdown, win rate,
periods processed, a presentational "successful/total (%)" success
ratio — no dedicated backend field, the same "X of Y" derivation M4's
screening results table established — and failed periods), a
portfolio-vs-benchmark bar chart, a drawdown curve (computed
client-side per period using the same peak-to-trough formula the
backend's own `max_drawdown` uses, documented as presentational — its
maximum always equals `BacktestResult.max_drawdown`), an interactive
timeline (Portfolio/Benchmark/Both toggle, amber `ReferenceDot`
markers only when `backtest-markers-store` has an entry for this run),
and a client-side-searchable periods table (`GET /backtests/{run_id}`
returns every period unpaginated — no server-side filter exists, the
same reasoned exception M4/M5 established for screening/signal
results).

## 4. Explainability & Performance Attribution

`features/historical-analysis/explainability/`: a generate form
(name + a required recommendation-result dropdown + three optional
strategy/risk/backtest-run dropdowns, all sourced from session history,
§1) and a result panel composing four sections — recommendation
explanations (per-candidate score/confidence/reasoning + top-positive/
top-negative/all-contributing factor lists), strategy explanations
(matched/failed `RuleAlignment`s reused directly from `app/strategy
/models.py`, never recalculated), a risk explanation (`category
_breakdown` reuses `RiskMetric`'s own taxonomy — deliberately *not*
remapped onto `AttributionCategory`, per the backend's own docstring —
plus severity counts and sector/country exposure bars), and Performance
Attribution (`features/historical-analysis/attribution/performance-
attribution-panel.tsx`, §1/§2): three return metric cards, a category-
distribution pie chart over the full `contribution_breakdown`, and
sector/country/industry bar charts each filtering that same array by
`category` — no separate attribution fetch, it's all one already-
fetched `ExplainabilityResult`.

## 5. Comparison mode

`features/historical-analysis/comparison/`: `backtest-compare-page.tsx`
and `explainability-compare-page.tsx` both mirror M5's research/
screening comparison pattern exactly — a field-by-field diff table over
exactly two already-fetched results (selected via `comparison-store.ts`,
capped at 2, newest bumps oldest), amber-highlighted where they differ,
zero new computation. No compare/diff endpoint exists on the real
backend for either domain (confirmed via a repo-wide grep) — this is
necessarily, not just conveniently, client-side.

## 6. Charts

`features/historical-analysis/charts/`: portfolio-vs-benchmark (3-bar),
drawdown curve (area), contribution distribution (pie, grouped by
category), and a generic attribution bar chart reused for sector/
country/industry — all Recharts, all backend-data-only. Per-segment
coloring uses the `shape` render-prop + `Sector`/`Rectangle` pattern
the dashboard and M5 charts already established, not `Cell` (deprecated
in this Recharts version — caught by lint). One workspace-wide chart
preference (`showDataLabels`, `historical-analysis-ui-store
.chartPreferences`) mirrors M5's identical per-workspace toggle,
scoped to its own store rather than sharing M5's.

## 7. State management

Unchanged split (TanStack Query = server state, Zustand = client
state), with three new/extended stores: `historical-analysis-ui-store.ts`
(timeline metric selection, chart preferences, the periods-table search
filter — all pure UI state, never server data), `backtest-markers
-store.ts` (§1, session-only, deliberately not persisted for the same
reason `decision-history-store.ts` isn't), and two extensions to
existing M5 stores — `decision-history-store.ts` gained `backtest_run`/
`explainability_generated` entry kinds (also the snapshot-builder's id
source, §1), and `comparison-store.ts` gained `backtestRunIds`/
`explainabilityRequestIds` (both capped at 2, identical bump-oldest
logic to the existing research/screening fields).

## 8. Notifications

Backtest started/completed and explainability generated all fire from
their mutation's `onMutate`/`onSuccess` (standard convention since M2);
backtest completion's message reports signed portfolio/benchmark
returns. API errors are automatic via the existing global `QueryCache`/
`MutationCache` handlers — no per-domain wiring needed.

## 9. Navigation

The M2-era `/backtesting` and `/explainability` `ComingSoon` placeholder
nav items were removed and folded into one new `/historical-analysis`
nav item (icon 🕰, permission `backtest:read`) — the sidebar and
dashboard quick-nav needed no code changes, both already read
`FEATURE_NAV_ITEMS` generically, the same zero-touch fold M5 established
for `/decisions`. This is the last such fold: all 7 original M2 domains
now have real pages, and `FEATURE_NAV_ITEMS` has no remaining
`ComingSoon` target.

## 10. Export

`components/export-placeholder-menu.tsx` — three disabled PDF/CSV/JSON
buttons with explanatory tooltips, reused by both the backtest detail
page and the explainability result panel. No export endpoint (PDF/CSV/
JSON) exists anywhere on the real backend (confirmed via a repo-wide
grep) — per the milestone's own explicit instruction, this stays a UI
placeholder, not a client-side-generated file.

## 11. Testing strategy

Same stack as M1–M5. New MSW test infrastructure: `test/msw/
backtesting-store.ts` and `explainability-store.ts` — unlike M4/M5's
`result-store.ts` (an `InMemoryResultStore` mirror), these model the
real backends' *durable* repositories (§1): a seeded run/result stays
gettable for the rest of the test, and both expose a `seed*` function
so detail-page/comparison tests can assert against known, hand-picked
values without going through the full create/generate flow every time.
`explainability-store.ts`'s mock `generateExplanation` correlates its
`performance_attribution` with an already-created backtest's real
`portfolio_return`/`benchmark_return` when a `backtest_run_id` is
supplied, rather than fabricating unrelated numbers.

**One real bug found and fixed, not just written around**: four
components (`historical-analysis-history-list.tsx`, `run-history
-list.tsx`, `snapshot-builder.tsx`, `generate-explanation-form.tsx`)
initially filtered `decision-history-store`'s `entries` array *inside*
their Zustand selector (`useDecisionHistoryStore((state) => state
.entries.filter(...))`). Because `.filter()` returns a new array
reference on every call, this triggers React's "the result of
getSnapshot should be cached" infinite-render-loop warning/error under
`useSyncExternalStore` — caught immediately by the new real-router
tests for `/historical-analysis` and its child routes (`Maximum update
depth exceeded`), not by inspection. Fixed by selecting the stable
`state.entries` reference and filtering in the component body instead,
matching the pattern M5's own `decision-history-list.tsx` already used
correctly.

**Coverage by spec area**: backtest creation (form validation, snapshot
builder from session history including its own empty state,
`create-backtest-form.test.tsx`), backtest detail (summary metrics,
periods table + search, timeline including marker presence/absence,
comparison toggle, error state, `backtest-detail-page.test.tsx`),
explainability generation (required-recommendation validation,
`generate-explanation-form.test.tsx`), all four explanation sections
plus performance attribution (populated and "not supplied" fallback
states, comparison toggle, `explainability-result-panel.test.tsx`),
both comparison pages (empty state, field-diff highlighting, clear
selection), the landing page and session history list (filtering out
non-Historical-Analysis entry kinds), charts (rendered without
crashing — jsdom's `ResponsiveContainer` limitation documented since
M1, so chart assertions check the surrounding panel heading, not
chart-internal SVG), hook-level coverage for both domains'
mutations/queries including 404 handling (`use-backtesting.test.tsx`,
`use-explainability.test.tsx`), and four new real-router tests
(`/historical-analysis`, `/historical-analysis/backtests`,
`/historical-analysis/backtests/$runId`, `/historical-analysis
/explainability`, `/historical-analysis/explainability/$requestId`)
alongside M2–M5's existing ones — replacing `routing.test.tsx`'s old
`/backtesting`-targeting `ComingSoon` test, whose target route and
entire premise (a stable placeholder route existing at all) no longer
exist after this milestone's nav fold (§9); the generic permission-
gated-route mechanism it covered is now asserted against
`/historical-analysis` instead. Accessibility follows the unchanged
M1–M5 convention: every interaction driven through `getByRole`/
`getByLabelText`, no separate assertion suite.

## 12. Known mocked/gap areas

- **The snapshot builder and the explanation-generation form can only
  offer ids from this browser session's own activity** (§1) — there is
  no backend endpoint to list/search existing recommendation/strategy/
  risk results, so a fresh session with no prior Decision Center
  activity has nothing to pick from (an explicit empty state, not a
  broken picker).
- **Timeline recommendation markers only exist for backtests created in
  the current session** (§1) — a run loaded by id from an earlier
  session, or after a page reload, shows the timeline with no markers
  and an explanatory note, because the backend itself never retains the
  snapshot→period mapping.
- **Performance Attribution is a single-snapshot panel, not a time
  series** (§1) — there is no per-period-over-time attribution data
  anywhere in the backend to plot.
- **Export is a UI placeholder only** (§10) — no PDF/CSV/JSON generation
  exists, by explicit milestone instruction pending backend support.
- **No compare/diff endpoint exists for either domain** (§5) —
  comparison is necessarily 100% client-side.
