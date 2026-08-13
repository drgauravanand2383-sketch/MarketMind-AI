# MarketMind AI Frontend — Milestone 5: Investment Decision Center

Builds the Investment Decision Center — Portfolio Recommendations,
Strategy Evaluation, Risk Analytics, Signals, and Alerts presented as
one coherent workspace — on top of Milestones 1–4 (`docs/frontend/
ARCHITECTURE.md`, `MILESTONE_2.md`, `MILESTONE_3.md`, `MILESTONE_4.md`,
still the primary references for the shell, auth, dashboard, and the
established CRUD/optimistic-update/testing conventions this milestone
reuses). No Backtesting or Explainability UI exists yet — those
permission-gated routes remain the M2 `ComingSoon` placeholders.

## 1. Backend research, not backend changes

Unlike Milestones 1, 3, and 4, this milestone required **zero backend
changes** — every endpoint the spec needed already existed
(`app/api/v1/portfolio`, `strategies`, `signals`, `alerts`). The work
instead was a full research pass against the real source (not the
Sprint 58 doc's summary alone) to nail down field-for-field shapes and
surface genuine capability gaps *before* writing any frontend code —
the same "confirm against real source, ask before assuming" discipline
M1/M3/M4 established for backend gaps, applied here to backend
*research* instead. Three architectural questions were resolved with
the user before implementation, all approved as recommended:

1. **`Alert` has no field linking it to a `Recommendation`** (only
   `rule_id`/`ticker`/`signal_name`, `app/alerts/models.py`) — resolved
   as a **client-side ticker match**, clearly labeled "(inferred)"
   everywhere it's shown, never presented as a backend-asserted
   relationship (`features/decision-center/alerts/related-recommendation.ts`).
2. **`POST /portfolio/recommendations` requires caller-supplied
   `CandidateEvidence[]`** (the engine never fetches Screening/Signals/
   Alerts/Research itself) — resolved as **minimal identity-only**
   candidate entry (ticker/company/sector/country/industry), the same
   manual-entry pattern M4 established for research/screening; evidence
   attachment (research reports, screening results) is explicitly out
   of this milestone's UI scope, though `CandidateEvidence` is modeled
   in full since the request schema accepts it.
3. **No shared "decision id" ties the five domains together** —
   Recommendations/Risk are `portfolio_id`-keyed; Strategy needs an
   explicit `recommendation_result_id`; Signals/Alerts have no
   portfolio concept at all. Resolved as **"portfolio-centered, partial
   sync"** (§5): the workspace holds a selected portfolio and threads
   the loaded `RecommendationResult.request_id` into Strategy; Signals
   and Alerts are decoupled tools within the same workspace shell.

Two further gaps had one clearly-correct resolution, not requiring a
question (mirroring M4's "no company search" precedent):

- **Risk has no flat `diversification_score`/`concentration_score`/
  `liquidity_score`/`volatility_score`** — these exist only as entries
  inside `risk_metrics`, keyed by `category`. Derived by filtering, never
  invented (`features/decision-center/risk/derive-risk-scores.ts`).
- **No `GET /alerts/rules` endpoint exists anywhere** — `rule_ids` can
  only ever be sent empty ("every enabled rule"); there is no rule
  picker UI because there is nothing to list (`@/types/alerts`'s module
  docstring).

## 2. Domain architecture

`src/types/strategy.ts`, `signals.ts`, `alerts.ts` are new, mirroring
`app.strategy.models`, `app.signals.models`, `app.alerts.models`
field-for-field. `src/types/portfolio.ts`'s `RecommendationCandidate`
was upgraded from M3's placeholder `supporting_signals: unknown[]` /
`supporting_alerts: unknown[]` to the real `SignalResult[]`/`Alert[]`
types now that both domains exist. Two easy-to-get-wrong shapes worth
calling out:

- **`RecommendationCandidate.confidence` and `RecommendationSummary
  .average_confidence` are on a 0–100 scale**, not 0–1 like Research's
  `overall_confidence` — confirmed against `app/recommendations/
  engine.py`'s own `f"...confidence {confidence}%..."` formatting. A
  stale M3 test fixture (`testRecommendationResult.summary
  .average_confidence: 0.8`, never actually rendered until this
  milestone) had this wrong; fixed as part of building real M5 tests
  against it, not a change made blind.
- **`SignalCondition.field`/`StrategyRule.field` are not flat names** —
  Signals use a dotted `"<namespace>.<field>"` path into one of four
  Market Data Abstraction Layer models (`quote`/`profile`/
  `fundamentals`/`ratios`, `features/decision-center/signals/
  signalable-fields.ts`); Strategy rules reference `RecommendationCandidate`'s
  own scalar fields directly.

## 3. Recommendations

`features/decision-center/recommendations/`: a generate form (identity-
only candidate rows, `useFieldArray`, mirrors M4's batch-research
form), a summary-cards strip (strong-buy/buy/watch/hold/avoid counts +
average score/confidence), a client-side sortable/filterable/
searchable candidate list, and a detail panel — score breakdown across
all six component scores, reasoning, supporting signals, supporting
alerts. There is no `GET /portfolio/recommendations/{id}` — detail is
always sliced client-side from the one already-fetched
`RecommendationResult`, the same reasoned exception M4 established for
screening results (no server list/sort/filter for a single-array
response). **Deliberately not optimistic** — the explicit Milestone 5
instruction ("Do NOT optimistically update recommendation data") is
honored literally: `useGenerateRecommendations` has no `onMutate`
cache write, only `onSuccess`.

## 4. Strategy Evaluation

`features/decision-center/strategy/`: an evaluate form (optional
multi-select of existing strategies — empty means "every strategy," a
single call), a comparison table (server-ranked `strategy_matches`,
best strategy highlighted), and a match-detail panel (matched/failed
rules, each a **population-level pass rate**, never a per-candidate
verdict — `StrategyMatch` has no `ticker` field on the real backend,
confirmed). "Strategy comparison" needed no separate UI or endpoint:
evaluating with an empty `strategy_ids` already returns every strategy
ranked in one response.

## 5. Risk Analytics

`features/decision-center/risk/`: overall score/severity, four derived
category-score cards (§1), a risk-category bar chart, sector/country
exposure pie charts plus a plain weighted-bar breakdown, a full
risk-metrics table, and the summary/recommendations text. Risk is
**GET-only** — no `POST` exists anywhere to trigger a new assessment,
confirmed via `docs/architecture/INTELLIGENCE_API.md`'s own explicit
note — so there is no "generate" button, only a 404-means-unavailable
empty state (the exact M3 `usePortfolioRisk` convention, unchanged).
The "Risk loaded" notification (§7) needed a small dedicated hook,
`use-risk-loaded-effects.ts`, since TanStack Query v5 dropped
`useQuery`'s `onSuccess` callback and Risk has no mutation to hang a
`notify()` off of otherwise.

## 6. Signals & Alerts

`features/decision-center/signals/`: a definition picker (`GET
/signals/definitions`), an evaluate form scoped to only the
dotted-path fields the *selected definition's own conditions*
reference (mirrors M4's `RunScreeningPanel` scoping — never all ~35
Market Data fields), and a results view with client-side
grouping-by-category, sorting, filtering, priority badges, and an
expandable triggered/failed-conditions detail per result. Signal
Detection has no portfolio concept whatsoever — this tab never reads
the selected portfolio.

`features/decision-center/alerts/`: since `POST /alerts/evaluate`
needs `SignalResult[]` inline and no endpoint produces one except
`POST /signals/evaluate` itself, the Alerts tab **chains directly off
the most recent Signals-tab evaluation** in the same session — a cache
hit against `useDecisionHistoryStore`'s latest `signals_evaluated`
entry plus `useSignalResult`, not a re-fetch or a manual signal-entry
form. `rule_ids` is always sent empty (§1) — there is no rule-picker
UI. The alert list is genuinely `GET /alerts`-paginated/sorted
server-side, with priority/status filtering client-side over the
fetched page only (no filter query params exist on the real endpoint).

## 7. Decision Center & Workspace

`decision-center-landing-page.tsx` is a portfolio picker (the user's
own watchlists — `portfolio_id` *is* `watchlist_id`, unchanged since
M3) plus the session decision history. `decision-workspace-page.tsx`
is the tabbed shell: a standard ARIA `tablist`/`tab`/`tabpanel` pattern
(`decision-workspace-tabs.tsx`), six tabs (Overview/Recommendations/
Strategy/Risk/Signals/Alerts), all driven by `useDecisionWorkspaceStore
.activeTab` — no sub-routing, per the spec's own "Zustand only for...
selected tabs" instruction. Overview synthesizes whatever the
Recommendations/Risk tabs already have loaded (cache hits, never a new
fetch) with shortcut buttons into each tab. `/recommendations` and
`/risk` (separate M2-era nav items) were removed and folded into one
new `/decisions` nav item — the sidebar and dashboard quick-nav needed
no code changes, both already read `FEATURE_NAV_ITEMS` generically.

## 8. Charts

`features/decision-center/charts/`: recommendation score distribution
(bucketed into fixed 20-point ranges), risk category breakdown (bar,
colored by severity), sector/country exposure (pie), strategy
alignment (bar, ranked), signal category distribution (pie) — all
Recharts, all backend-data-only (bucketing/counting for chart shape is
the one allowed presentation computation, same as M2's dashboard
`HealthSummaryChart`). Per-slice/per-bar coloring uses the `shape`
render-prop + `Sector`/`Rectangle` pattern the dashboard charts already
established, not `Cell` (deprecated in this Recharts version — caught
by lint, not by inspection). One workspace-wide chart preference
(`showDataLabels`, toggled via `useDecisionWorkspaceStore
.chartPreferences`) satisfies the spec's "chart preferences" UI-state
requirement without inventing a preference per chart.

## 9. State management

Unchanged split (TanStack Query = server state, Zustand = client
state), with three new stores: `decision-workspace-store.ts` (selected
portfolio, active tab, the threaded recommendation-result id, chart
preferences), `alerts-ui-store.ts` (the alert list's sort/page/
client-filters, mirrors M4's `screening-ui-store.ts`), and
`decision-history-store.ts` (session-only activity across all five
domains — a discriminated-union `DecisionHistoryEntry[]`, the same
non-persisted "this session" convention M4's `session-activity-store.ts`
established, for the identical reason: none of the five domains have a
durable, cross-session, listable history to back a real one).

## 10. Notifications

Recommendation generated, strategy evaluation completed, and alert
evaluation completed all fire from their mutation's `onSuccess`
(standard convention since M2). Risk loaded is the one exception (§5)
— a query-driven effect, not a mutation callback, since Risk has no
`POST`. API errors are automatic via the existing global `QueryCache`/
`MutationCache` handlers — no per-domain wiring needed, and no
optimistic mutations exist in this milestone to need
`suppressErrorToast`.

## 11. Testing strategy

Same stack as M1–M4. New MSW test infrastructure:
`test/msw/decision-center-store.ts` (seeded strategies/signal-
definitions/alert-rules — the last of which the frontend itself never
sees, since no rule-listing endpoint exists, but the mock evaluator
needs *something* to check signals against) and `test/msw/
decision-center-evaluator.ts` (a shared, real-enough-for-tests operator
evaluator — all 9 operators — reused across the strategy/signal/alert
mock handlers, mirroring M4's `screening-evaluator.ts`). One
correctness fix to the mock strategy-results cache: it now keys by the
evaluation's own `request_id` (matching the real backend's "`result_id`
*is* the request id" convention) rather than a separately-generated
cache id — a bug the hook test's own re-fetch assertion caught
immediately, not something inspection would have found.

**Two real regressions in pre-existing M3 tests, found and fixed, not
just written around**: fixing `testRecommendationResult`'s stale 0–1
confidence value (§2) also meant its `recommendations: []` /
`total_candidates: 3` mismatch became visible for the first time — the
existing M3 `watchlist-detail-page.test.tsx` assertion of "3
candidates" broke until the fixture was given three real, mutually
consistent candidates instead of an empty array. Separately, removing
the M2-era `/recommendations` nav item (§7) broke `dashboard-
page.test.tsx`'s assertion that a "Recommendations" quick-nav card
existed — updated to expect "Decision Center." Both were caught by a
full-suite run before this milestone was considered complete, not
assumed passing from the scoped test files alone.

**Coverage by spec area**: recommendation workflow (generate, list,
sort/filter/search, detail — `recommendations-panel.test.tsx`), strategy
display (`strategy-panel.test.tsx`, comparison + matched/failed rules),
risk display (`risk-panel.test.tsx`, including the 404-unavailable
state and the notify-once guarantee), signals (evaluate + scoped form +
grouping, `signals-panel.test.tsx`), alerts (chained evaluate +
priority filter, `alerts-panel.test.tsx`), filtering/sorting (client-
side list tests throughout), charts (rendered without crashing —
jsdom's lack of a real layout engine means Recharts' `ResponsiveContainer`
doesn't produce meaningful SVG internals in tests, the same limitation
M1–M3 documented for responsive/adaptive layout, so chart assertions
check the surrounding panel mounts, not chart-internal DOM), decision
workspace (`decision-workspace-page.test.tsx` — real ARIA tablist
semantics, tab switching, store sync), accessibility (every interaction
driven through `getByRole`/`getByLabelText`, unchanged M1–M4
convention), MSW-backed integration (every test above), and hook-level
coverage for all five domains' server-state hooks
(`use-portfolio.test.tsx`'s new cases, `use-strategy.test.tsx`,
`use-signals.test.tsx`, `use-alerts.test.tsx`) plus two new real-router
tests (`/decisions`, `/decisions/$portfolioId`) alongside M3/M4's
existing ones.

## 12. Known mocked/gap areas

- **"Related recommendation" on an Alert is a client-side ticker-match
  inference**, never a backend-asserted relationship (§1) — labeled
  "(inferred)" everywhere shown.
- **"Generate recommendations" only collects candidate identity**, not
  evidence (screening/research/signals/alerts attachment) — by
  explicit product decision (§1), not a technical limitation of
  `CandidateEvidence` itself (which is modeled in full and does accept
  evidence, unused by this milestone's UI).
- **No alert-rule picker exists** — `rule_ids` is always empty ("every
  enabled rule") because no REST endpoint lists `AlertRule`s at all.
- **Decision history is session-only**, not durable, for the same
  reason M4's research/screening history is (§9) — none of the five
  domains persist a listable history across the backend's own
  lifetime, let alone across sessions.
- **No "generate a new risk assessment" action exists** — Risk is
  GET-only on the real backend; this is a genuine API-surface gap, not
  an oversight.
