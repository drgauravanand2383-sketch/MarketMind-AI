# Continuous Intelligence & Decision Automation

**Milestone 15 — post-v1.0.0 / v1.1 candidate.** Turns MarketMind from a
request-driven intelligence system into one that detects meaningful
changes and proactively surfaces them. v1.0.0's own scope, status, and
sign-off are unchanged by this document. See
`docs/release/UPGRADE_POLICY.md`'s versioning rules for what a v1.1
candidate capability means in this repository.

**No second business engine was created.** Every score, severity, and
evaluation this milestone reacts to is read from an existing engine's
already-computed output (`RiskAssessment`, `RecommendationResult`,
`StrategyEvaluationResult`, `SignalResult`, `MarketSnapshotResult`) —
never recomputed with new logic here. No second alert engine, no second
recommendation engine.

## 1. Architecture — what composes what

Per §1's own instruction, the existing systems were inspected before any
new code was written:

- **Scheduler/WorkflowEngine** (`app/scheduler/`, `app/workflows/engine.py`):
  `Schedule.enabled` gates both automatic *and* manual execution — one
  switch, not two. No generic "register a workflow" helper exists;
  `register_ingestion_schedule`/`register_market_data_schedule` are
  hand-written, near-identical pairs. `register_continuous_intelligence_
  schedule` (this milestone) follows the exact same pattern.
- **MorningPipeline**: ingests RSS -> embeds -> writes to
  `KnowledgeRepository` -> entity-resolves, on its own existing schedule.
  Continuous Intelligence never re-runs ingestion — it reads the
  already-ingested state via `KnowledgeHub.query()`, the same read path
  `PortfolioIntelligenceAgent`/`CompanyResearchAgent` already use.
- **MarketDataRefreshWorkflow** (Milestone 13): its own
  `MarketDataRefreshResult` carries only the *newly*-fetched snapshot,
  never a previous one — `InMemoryMarketSnapshotCache.get()` returns
  whatever is currently cached with no history API. This milestone
  therefore keeps its own separate previous-state store (§4) rather than
  extending that cache.
- **RiskAnalyticsService / PortfolioRecommendationService /
  SignalDetectionService / AlertService**: all four are pure, on-demand,
  no-self-trigger engines (confirmed by inspection, Milestone 14's own
  finding, reaffirmed here) — none of them re-run themselves periodically
  today. See §16 for what this means for Risk/Recommendation detection.
- **WebSocket event publisher / Notification Center / realtime
  invalidation**: all reused exactly as built in Sprint 59/Milestone
  7 — three new event types (§9), zero changes to `ConnectionManager`,
  `SubscriptionRegistry`, or the WS wire protocol.
- **AlertService cooldown/dedup**: `_is_duplicate()`'s named-field-tuple
  comparison (`ticker`/`signal_name`/`priority`/`rule_id` + `cooldown_
  minutes`) is the only existing dedup precedent in this codebase — no
  hash/fingerprint concept exists anywhere else. `SuppressionService`
  (§5) mirrors this shape deliberately rather than inventing a new one.

New code: `app/services/continuous_intelligence/` (detector, state,
suppression, decision-impact, config, models, the orchestrating
`ContinuousIntelligenceService`) and `app/workflows/continuous_
intelligence/` (a thin `WorkflowProtocol` adapter).

```
ContinuousIntelligenceWorkflow.execute()
        |
        v
ContinuousIntelligenceService.run_cycle()
        |
        +--> MarketSnapshotService.get_snapshots(use_cache=False)   (Milestone 13, reused)
        +--> KnowledgeHub.query() + MarketIntelligenceEngine.analyze()  (existing, reused)
        +--> SignalDetectionService.evaluate_company()               (existing, reused)
        |         --triggered--> AlertService.evaluate_rules()       (existing, reused, own cooldown)
        +--> RiskAnalyticsService.list_requests()/.get_assessment()  (existing, reused, read-only)
        +--> PortfolioRecommendationService.list_requests()/.get_result()  (existing, reused, read-only)
        |
        v
ChangeDetectionService (NEW, pure/deterministic)
        |
        v
DecisionImpactService (NEW, read-only WatchlistService composition)
        |
        v
SuppressionService (NEW, cooldown-based dedup)
        |
        v
EventPublisher.publish_significant_market_change/_news_update/_portfolio_intelligence_changed  (NEW methods, existing framework)
```

## 2. Change detection

`ChangeDetectionService` (`app/services/continuous_intelligence/detector.py`)
— one `detect_*` method per category, each pure (no I/O), each comparing
an already-fetched current value against `InMemoryContinuousIntelligenceStateStore`'s
previously-observed value for the same key:

| Category | Compares | §2 source |
|---|---|---|
| Market | `MarketSnapshotResult.status`/`.snapshot.price` vs previous | 2A |
| News | Set of `KnowledgeRecord.id`s returned for a canonical entity's own name, vs previous set (new ids = new evidence) | 2B |
| News confidence | `MarketIntelligenceEngine`'s own `NewsGroup.confidence_score` for that entity vs previous | 2B |
| Signal | `SignalResult.triggered` vs previous, per (entity, `SignalDefinition.id`) | 2C |
| Risk | `RiskAssessment.overall_severity` vs previous, per portfolio | 2C |
| Recommendation | `RecommendationCandidate.recommendation`/`.overall_score` vs previous, per (portfolio, ticker) | 2C |
| Strategy | `StrategyEvaluationResult.overall_alignment` vs previous, per portfolio (detector implemented, **not wired into the automatic cycle** — see §16) | 2C |

Every method returns `DetectedChange | None` — `None` covers both "first
observation, nothing to compare against" and "compared, not significant."
**A scheduler run producing zero `DetectedChange`s is the expected,
correct outcome most cycles** — §2's own "do not emit an event simply
because a scheduler ran" instruction is satisfied by construction, not by
a special case.

## 3. Significance rules

Every threshold is a named field on `ContinuousIntelligenceThresholds`
(`app/services/continuous_intelligence/config.py`), never an unexplained
literal inline in a detector:

| Field | Default | Meaning |
|---|---|---|
| `market_change_percent_threshold` | `3.0` | Minimum `\|change_percent\|` for a market move to be significant. |
| `news_significance_threshold` | `2` | Minimum newly-seen record count for one entity since the last cycle. |
| `news_high_confidence_threshold` | `0.75` | `NewsGroup.confidence_score` an entity's evidence must *newly* cross. |
| `recommendation_score_delta_threshold` | `10.0` | Minimum `overall_score` delta (0-100) when `RecommendationType` itself didn't change. |
| `strategy_alignment_delta_threshold` | `10.0` | Minimum `overall_alignment` delta (0-100). |
| `suppression_cooldown_minutes` | `60.0` | How long an identical fingerprint is suppressed after being emitted (§5). |

Risk/Signal have no separate numeric threshold — both compare a
*categorical* value (`RiskSeverity`, `triggered: bool`) where any genuine
transition is already significant by definition; no magnitude band is
meaningful there.

**Priority banding for magnitude-based categories** (Market/News/
Recommendation-by-score/Strategy):
`priority_from_magnitude(magnitude, threshold)` — `>= 8x` threshold =
`CRITICAL`, `>= 4x` = `HIGH`, `>= 2x` = `MEDIUM`, otherwise `LOW` (a
change must already be `>= 1x` threshold to exist as a `DetectedChange`
at all). Risk/Signal/Recommendation-by-type use direct, deterministic
maps from their own existing categorical enum instead (§7).

## 4. State comparison

**Milestone 16 update:** state comparison now has two implementations of
the same async interface (`ContinuousIntelligenceStateStore`,
`app/services/continuous_intelligence/state.py`):
`InMemoryContinuousIntelligenceStateStore` (below, unchanged from
Milestone 15) and `PostgresContinuousIntelligenceStateStore` (durable,
restart-safe). Which one is active depends on whether a PostgreSQL
repository was reachable at startup — see
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` for the full
persistence design (schema, restart semantics, locking, suppression).
This section describes the in-memory implementation, still the fallback
whenever Postgres is unavailable.

`InMemoryContinuousIntelligenceStateStore`
(`app/services/continuous_intelligence/state.py`) — a plain, process-local
set of dicts, one per category, keyed by entity id / `"{portfolio_id}:
{ticker}"` / `"{entity_id}:{signal_definition_id}"` as appropriate.

**Restart semantics, explicit** (§4's own requirement): every store is
lost on process restart, exactly like `InMemoryMarketSnapshotCache`
(Milestone 13). This never causes a flood of duplicate "changes": every
`observe_*` method returns `None` for a key it has never seen, and every
detector treats `None` as "nothing to compare against yet" — never as
"changed from nothing." The first cycle after a restart therefore detects
**zero** changes for every previously-tracked key, by construction, not by
a special-cased check the detectors have to remember. Verified directly:
`tests/services/continuous_intelligence/test_service.py
::test_restart_is_simulated_by_a_fresh_service_instance` (in-memory) and
`::test_postgres_backed_service_restart_does_not_duplicate_and_still_detects_new_change`
(Postgres-backed, Milestone 16).

## 5. Deduplication & event identity

`DetectedChange.fingerprint` (`app/services/continuous_intelligence/models.py`)
is a stable, inspectable string key — `"{DOMAIN}:{entity_id}:{detail}"`
(e.g. `"MARKET:dell:price:<fetched_at>"`, `"RISK:wl-1:HIGH"`,
`"SIGNAL:dell:def-1:True"`) — never a hash. This mirrors `AlertService
._is_duplicate`'s own named-field-key approach rather than inventing a
new dedup primitive.

**Portfolio fan-out gets a portfolio-scoped fingerprint.** When Decision
Impact (§7) expands one portfolio-agnostic change (Market/News/Signal)
across every watching portfolio, each expanded copy's fingerprint gets
`:{portfolio_id}` appended. Without this, a shared fingerprint across
portfolios would let the *first* portfolio's copy suppress every other
portfolio's copy of the exact same underlying change — a real bug caught
during this milestone's own test-writing and fixed before release; see
`tests/services/continuous_intelligence/test_service.py
::test_market_change_notifies_every_watching_portfolio_independently`.

**`DetectedChange.event_fingerprint` (v1.2 Priority 1).** The
per-portfolio scoping above is deliberate and correct for suppression,
but it means `fingerprint` alone can no longer answer "are these two
`DetectedChange`s the same real-world event, just routed to different
portfolios?" — a real, evidence-backed gap: the v1.1.1 pilot observed a
single Dell price move surface as three visually-identical
`DetectedChange`s in one cycle (one per watching portfolio), with no
field connecting them back to "one underlying event." `event_fingerprint`
is set once, at detection time, to the same value `fingerprint` would
have had before any portfolio expansion — `attach_portfolio_context`
copies `portfolio_id` and rewrites `fingerprint`, but never touches
`event_fingerprint`. This is deliberately *not* a cross-portfolio
grouping/deduplication mechanism — the pilot's redundant-notification
finding was logged as a separate, deferred P2, and grouping still isn't
implemented — it only guarantees the stable identity survives portfolio
expansion so a future task can group on it without a further schema
change. See `test_attach_portfolio_context_preserves_event_fingerprint_across_expansion`.

Because the detector layer already blocks re-detecting an unchanged
value (§2 — same value in, `None` out), the same fingerprint recurring
within a cooldown window mainly happens when a value **oscillates**
(e.g. `LOW -> HIGH -> LOW -> HIGH` across cycles) — each transition is
genuinely detected, but the *second* `HIGH` shares its fingerprint with
the first. That is exactly what §5/§8 ask suppression to catch; see
`test_oscillating_risk_severity_is_suppressed_within_cooldown`.

## 6. Suppression / alert-storm protection

**Milestone 16 update:** same two-implementation pattern as §4 —
`SuppressionService` (in-memory) and `PostgresSuppressionService`
(durable), both satisfying the `Suppression` interface. See
`docs/architecture/CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` for why
suppression durability matters: an in-memory-only suppression record lost
at exactly the wrong moment (a restart just after emitting, just before a
duplicate would have arrived) re-emits a notification that should have
stayed suppressed.

`SuppressionService` (`app/services/continuous_intelligence/suppression.py`)
— `fingerprint -> last-emitted-at`, in-memory (same restart semantics as
§4). `is_duplicate(fingerprint)` compares elapsed time against
`suppression_cooldown_minutes`; `record_emitted(fingerprint)` is called
only for changes that actually get published. A deliberately separate
service from `AlertService`'s own cooldown — reusing `AlertService`
directly would mean fabricating fake `SignalResult`/`AlertRule` objects
for every market/news/risk/recommendation change just to reach its
cooldown logic, which doesn't fit their shape. **`AlertService`'s own
cooldown/dedup is untouched** — every newly-`triggered` signal is fed
into the real `AlertService.evaluate_rules()` (§16), which decides
`GENERATED`/`SUPPRESSED` exactly as it always has, independent of this
milestone's own suppression layer.

## 7. Priority

`ChangePriority` (`INFO`/`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`) is a new,
5-tier scale — none of this codebase's three existing severity/priority
enums has exactly this shape (`AlertPriority`/`SignalPriority` have no
`INFO`; `RiskSeverity` has `MODERATE` not `MEDIUM`, no `INFO` either).
Not a second, incompatible system: every existing enum maps into it
deterministically —

```python
priority_from_alert_priority(AlertPriority) -> ChangePriority   # direct 1:1
priority_from_risk_severity(RiskSeverity) -> ChangePriority     # MODERATE -> MEDIUM, else 1:1
priority_from_signal_priority(SignalPriority) -> ChangePriority # direct 1:1
priority_from_magnitude(magnitude, threshold) -> ChangePriority # banding, §3
```

`INFO` is this scale's own bottom tier, used only where no existing enum
applies (e.g. a signal transitioning to `triggered=False`).

## 8. Decision impact

`DecisionImpactService` (`app/services/continuous_intelligence/decision_impact.py`)
answers "does this change matter to a portfolio?" — read-only composition
over `WatchlistService.list_watchlists()` only. **Never recalculates risk
or recommendations** — it only asks which existing watchlists reference
the ticker a Market/News/Signal change was detected for, then attaches
`portfolio_id` (§5's fingerprint-scoping applies here). Risk/
Recommendation/Strategy changes never reach this service — their own
detector methods already carry `portfolio_id` directly, computed
per-portfolio from the start.

## 9. Event types

Three new `EventType` members, added only because no existing type
accurately represents the new semantic event (§9's own instruction):

| Event | Why not an existing type |
|---|---|
| `SIGNIFICANT_MARKET_CHANGE` | `MARKET_SNAPSHOT_REFRESHED` (Milestone 14) reports "a refresh ran across every entity," not "this one entity moved meaningfully" — a fundamentally different granularity and semantic. |
| `SIGNIFICANT_NEWS_UPDATE` | No existing event type covers evidence-volume/confidence change at all. |
| `PORTFOLIO_INTELLIGENCE_CHANGED` | Reusing `RECOMMENDATION_GENERATED`/`RISK_ASSESSMENT_COMPLETED` for this would risk a literal duplicate notification: those already fire synchronously when a REST handler *creates* a new result (Milestone 14). This event fires *proactively*, with no request involved, when Continuous Intelligence *observes* an already-stored result changed — a different occurrence of a different kind, not a re-announcement of the same one. |

All three share one payload type, `DetectedChange` — consistent with
`BaseEvent`'s own "every payload reuses an existing domain model
directly" convention (`DetectedChange` *is* the new domain model this
milestone introduces, used directly, never wrapped again).

**Permission mapping** (`app/api/ws/dependencies/permissions.py`):
`PORTFOLIO_INTELLIGENCE_CHANGED` requires `portfolio:read` (matches its
REST-sourced siblings). `SIGNIFICANT_MARKET_CHANGE`/`SIGNIFICANT_NEWS_
UPDATE` require no specific permission — same reasoning as `MARKET_
SNAPSHOT_REFRESHED`: no per-portfolio scope, no REST source to inherit a
permission from, covers public canonical-entity price/news state.

**Trigger point**: `ContinuousIntelligenceWorkflow.execute()`, run
in-process by the live server's own scheduled execution — the same
reasoning Milestone 14 established for why an operational script cannot
usefully publish real-time events (it builds its own throwaway `FastAPI()`
app, sharing no `ConnectionManager` state with real connected clients).

## 10. User / portfolio scope

Per §11's own instruction, **no global "notify everyone" mechanism was
introduced.** This codebase has no per-user watchlist ownership model at
all (confirmed by inspection — `Watchlist` carries no `user_id`; a
`portfolio_id` *is* a `watchlist_id`, Milestone 14's own established
fact) — introducing one now would be an architecture redesign, explicitly
out of scope (§0's own "do NOT redesign the architecture"). Scope is
therefore enforced exactly the way every other WS event already enforces
it: **permission-gated subscription** (§9) plus the existing
`correlation_id` filter (`Subscription.correlation_id`, unmodified,
Sprint 59) — a client may subscribe narrowly to one portfolio's events
via `correlation_id="<portfolio_id>"`. `EventPublisher.publish_
portfolio_intelligence_changed()`'s `correlation_id` is `change.
portfolio_id or change.entity_id`, enabling exactly that.

## 11. Notification Center integration

`toNotificationEntry()` (`frontend/src/lib/realtime-notifications.ts`)
gained cases for all 5 currently-unmapped event types (2 from Milestone
14, previously a real gap — never wired into the frontend at all — plus
this milestone's own 3):

- `MARKET_SNAPSHOT_REFRESHED` / `PORTFOLIO_INTELLIGENCE_UPDATED` -> `null`
  (a refresh/fetch completing is not itself a proactive notice — see §9's
  own event-type table above).
- `SIGNIFICANT_MARKET_CHANGE` / `SIGNIFICANT_NEWS_UPDATE` /
  `PORTFOLIO_INTELLIGENCE_CHANGED` -> real `NotificationCenterEntry`s,
  three new `NotificationDomain`s (`"market"`/`"news"`/`"decisions"`),
  each deep-linking to `/decisions/$portfolioId` when Decision Impact
  attached one (`null` — plain button, no broken link — otherwise).

`ChangePriority`'s `INFO` tier maps to a `null` `PriorityLevel` (no
existing tier is equivalent); every other tier passes through unchanged.

## 12. Frontend realtime integration

No second realtime transport, per §13. `invalidateForEvent()`
(`frontend/src/lib/realtime-invalidation.ts`) gained cases using the
already-portfolio-scoped `portfolioKeys.intelligence/risk/recommendations(id)`
query keys (`frontend/src/hooks/use-portfolio.ts`) — surgical
invalidation only when `DetectedChange.portfolio_id` is present; a
portfolio-agnostic change invalidates nothing (no safe target).
`useRealtimeSubscriptions()` (`frontend/src/hooks/use-realtime-
subscriptions.ts`) was extended with the same ungated/gated split §9
describes. Duplicate-toast avoidance is unchanged — still `notification-
store.ts`'s own `(type, message)` equality check, one layer below where
these new events enter.

## 13. Scheduler & configuration

`register_continuous_intelligence_schedule` mirrors `register_market_
data_schedule` exactly: always registers the workflow (so the
operational "run now" trigger works regardless of the timer) and always
registers a `Schedule`, gated by one `enabled` switch.

| Setting | Default | Meaning |
|---|---|---|
| `CONTINUOUS_INTELLIGENCE_ENABLED` | `false` | Gates the scheduled cycle — same "never silently change an existing deployment's behavior" default as `INGESTION_ENABLED`/`MARKET_DATA_ENABLED`. |
| `CONTINUOUS_INTELLIGENCE_INTERVAL_SECONDS` | `900.0` | 15 minutes — between Market Data Refresh's own 3600s default and genuinely "continuous." |
| `MARKET_CHANGE_THRESHOLD` | `3.0` | -> `market_change_percent_threshold` |
| `NEWS_SIGNIFICANCE_THRESHOLD` | `2` | -> `news_significance_threshold` |
| `NEWS_HIGH_CONFIDENCE_THRESHOLD` | `0.75` | -> `news_high_confidence_threshold` |
| `RECOMMENDATION_SCORE_DELTA_THRESHOLD` | `10.0` | -> `recommendation_score_delta_threshold` |
| `STRATEGY_ALIGNMENT_DELTA_THRESHOLD` | `10.0` | -> `strategy_alignment_delta_threshold` |
| `CONTINUOUS_INTELLIGENCE_SUPPRESSION_COOLDOWN_MINUTES` | `60.0` | -> `suppression_cooldown_minutes` |
| `CONTINUOUS_INTELLIGENCE_LOCK_TTL_SECONDS` (Milestone 16) | `300.0` | -> `cycle_lock_ttl_seconds` — how long a `PostgresCycleLock` claim is honored before being treated as abandoned. |
| `CANONICAL_ENTITIES_OVERLAY_PATH` (Milestone 16) | unset | Optional path to a JSON file of additional canonical entities (§8, see `CONTINUOUS_INTELLIGENCE_PERSISTENCE.md`). |

**Milestone 16 — cycle-level locking**: `ContinuousIntelligenceService
.run_cycle()` now wraps its entire body in a `CycleLock` acquire/release,
so the same cycle can never run concurrently with itself regardless of
what triggered the second attempt (scheduler overlap, a manual
operational trigger, or a second process entirely). See
`CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` §"Concurrency / locking" for the
full design.

**Bootstrap ordering note**: this schedule's dependencies
(`watchlist_service`/`signal_detection_service`/`alert_service`/
`risk_service`/`recommendation_service`/`knowledge_hub`) are all built
*after* `ap_scheduler_service.start()`'s original call site (Milestones
11-13 never needed them before that point). `APSchedulerService.start()`
only picks up schedules present at the moment it runs, so its call was
moved to the end of `bootstrap_application_state`'s own service
construction, right after `register_continuous_intelligence_schedule` —
a mechanical reordering, not a behavior change for any existing schedule.

## 14. Operational execution

`scripts/run_continuous_intelligence.py` — mirrors `scripts/run_market_
data_refresh.py` exactly: container-exec only, triggers one real cycle
via `Scheduler.run_schedule()`, prints a JSON summary (every §19 count,
plus every individual detected/suppressed change — never just a count),
exits `0` on success (even zero changes), `1` if not registered,
disabled, or the cycle reported any failure.

## 15. Failure isolation

Every per-entity (market/news/signal) and per-portfolio (risk/
recommendation) block inside `ContinuousIntelligenceService.run_cycle()`
is individually `try`/`except`-wrapped — one bad ticker, one unavailable
service, or one publish failure never stops the rest of the cycle. Every
failure is appended to `ContinuousIntelligenceCycleResult.failures`,
never silently swallowed. A publish failure specifically does not lose
the underlying detected state — the change still counts as "emitted" and
`record_emitted()` still runs, so a repeat detection next cycle is still
correctly suppressed even if the WS broadcast itself failed. **Milestone
16**: a publish failure is now also logged (`continuous_intelligence
_publish_failed`) rather than silently caught and discarded — it was
previously swallowed by a bare `except: pass` with no observability at
all.

## 16. Risk / Recommendation / Signal / Strategy — what's automatic and what isn't

**Signal**: fully automatic. Every enabled `SignalDefinition` is
evaluated against each canonical entity's fresh `MarketDataSnapshot`
(via the Milestone 14 `signal_adapter`) every cycle — this is the same
composition pattern Milestone 14 already established, just run on a
schedule instead of on-demand. A newly-`triggered` signal is
additionally fed into the real, existing `AlertService.evaluate_rules()`
— Alerts become market-aware purely indirectly and automatically, with
zero new alerting logic.

**Risk / Recommendation**: **detected, never recomputed.** Neither
`RiskAnalyticsService.assess_portfolio()` nor `PortfolioRecommendationService
.generate_recommendations()` is ever called by this milestone — both
require evidence this cycle has no way to synthesize (screening results,
research reports, signal/alert evidence bundles), and no automatic
evidence-sourcing pipeline exists anywhere in this codebase. Each cycle
instead reads the *most recently stored* `RiskAssessment`/
`RecommendationResult` per portfolio (via each service's own
`list_requests`/`get_*`) and compares it to the previous cycle's —
detecting when something *else* (a user action, a future pipeline)
already changed the stored state, without inventing new computation.

**Strategy (Milestone 16 §12 — now wired in):** `StrategyEvaluationResult`
gained a `recommendation_result_id` field (nullable, additive — see
migration `0004_strategy_linkage`), populated from
`StrategyEvaluationRequest.recommendation_result_id` at evaluation time —
a value the service already legitimately received as a parameter but
previously never persisted. `ContinuousIntelligenceService._detect_strategy`
resolves a stored evaluation's portfolio via
`PortfolioRecommendationService.get_request(recommendation_result_id)
.watchlist_ids` — the exact same "*_result_id is actually a request id"
convention `RiskAssessmentRequest`/`ExplainabilityRequest`/`BacktestSnapshot`
already use. An evaluation stored *before* this field existed
(`recommendation_result_id is None`) is simply excluded from automatic
detection, never guessed at — verified by
`test_strategy_evaluation_without_recommendation_linkage_is_never_attributed`.
Only enabled when a `strategy_service` is injected (a soft dependency,
like `knowledge_hub` for News).

## 18. v1.2 Priority 1 — Selective Signals & High-Quality Alerts

The v1.1.1 real-world pilot found every alert this deployment had ever
generated (887 of them) scored exactly `confidence=100.0`/`score=100.0`,
with a generic, identical `reason` string regardless of what actually
happened. Root cause, traced end to end (not guessed): the live
`SignalDefinition` in production ("M14 Live Price Breakout") had exactly
**one** condition, `quote.price GREATER_THAN 100.0`, weight 1.0 — a
Milestone-14 live-acceptance-test fixture (see
`tests/services/portfolio_market_snapshot/test_market_data_to_alert_pipeline.py`'s
own `_price_signal_definition()`, an almost-identical pattern) that was
never replaced with a real production signal. With one condition,
`app.signals.engine._weighted_score` can only ever output 0.0 or 100.0 —
there is no weight to distribute. Every one of the 12 canonical entities
trades above $100, so the condition was, in effect, always true. This
was **not** hardcoded confidence in code — `SignalDetectionService`'s
weighted engine was, and remains, a correct, deterministic, evidence-
based calculator; it was simply fed a degenerate, single-condition
signal definition.

**Fix — genuinely graduated scoring, same engine, no new capability.**
`app/signals/reference_definitions.py` (new) assembles a replacement
"Live Price Breakout" definition from the *existing* `SignalCondition`/
`SignalConditionGroup` primitives: a same-day move of at least 5% in
either direction (`quote.change_percent`, two directional conditions
under one OR group — the engine has no "absolute value >=" operator) at
weight 3 each, AND a liquidity floor (`quote.price > 5.0`) at weight 1.
Because a real move can only ever satisfy one side of the OR group, a
genuine triggered breakout scores at most (3 + 1) / 7 ≈ 57.1%, never
100% — see the module's own docstring for the exact arithmetic, and
`tests/signals/test_reference_definitions.py` for the regression proof
across the pilot's own five real observed price moves (Dell, Salesforce,
Workday, Reddit, SanDisk).

**Fix — structured, evidence-based explanation (§4).**
`ConditionEvaluation` gained `actual_value`/`expected_value` (additive —
the same values `_apply_operator` already computed locally to build its
string `reason`, now also surfaced structurally). `app.alerts.models`
gained `AlertExplanation` — `signal_category`, `weighted_score`,
matched/failed condition counts, the real `ConditionEvaluation`s, and
`signal.reason` verbatim — attached to every new `Alert` via
`Alert.explanation` (nullable, additive; migration
`0006_alert_explanation`). `AlertService.evaluate_signal`'s `reason` no
longer reads `"Rule X matched signal Y for TICKER."` (identical for
every alert, regardless of outcome) — it now incorporates the signal's
own real weighted-match description.

**Selectivity — verified already correct, not re-architected.** Every
literal requirement this milestone's own brief listed
("a scheduled refresh alone must never produce an alert", "an unchanged
state must never produce an alert", "stale market data must not
generate a significant market alert", "a news ingestion event must not
automatically become an alert unless it meets significance criteria")
was checked against the actual code and found **already true**, with
existing test coverage (§2's own first-observation/threshold tests;
`signal_adapter.build_market_data_snapshot`'s FRESH-only guard, unit-
tested in `test_signal_adapter.py`) — nothing here needed a behavior
change, only an explicit end-to-end regression test
(`test_stale_market_data_never_produces_a_signal_or_alert`) proving the
consequence carries all the way through to "no alert candidate", not
just "no quote". Suppression/cooldown (§6) is unchanged — the fix is a
better-designed signal producing fewer, more meaningful alert
*candidates* in the first place, not a more aggressive suppression
policy compensating for a noisy one.

**`event_fingerprint`** — see §5 above.

## 19. v1.2 Priority 2 — Cross-Portfolio Notification Grouping

The v1.1.1 pilot's own separately-tracked P2 finding: the same
underlying event fans out to one WS broadcast **and one Notification
Center entry** per impacted portfolio — a real Dell price move surfaced
as 3 visually-identical notifications because 3 real watchlists tracked
Dell. v1.2 Priority 1 (§18) already gave every fanned-out copy a stable
`event_fingerprint`; this milestone uses it to collapse the *user-visible*
duplication without touching delivery, suppression, or portfolio scoping.

**Grouping key.** `event_fingerprint` only — never `fingerprint` (per-
portfolio, deliberately unique — §5), never `portfolio_id`, never a
notification UUID, never a timestamp alone. Two `DetectedChange`s group
together iff they share one `event_fingerprint`; a different entity, a
different domain (market vs. news for the *same* entity), or a
genuinely later occurrence of the same event (a new `fingerprint` once
the prior one's cooldown has expired and a fresh comparison baseline is
established) are never conflated.

**Where grouping happens, and where it deliberately does not.**
`ContinuousIntelligenceService._route()` (already the single place
portfolio fan-out and suppression both happen — §5/§8) computes the
group: it fans out (unchanged), applies suppression **per candidate,
independently, first** (unchanged — this is the load-bearing ordering
requirement, see below), and only *after* deciding which candidates
survive does it collect their `portfolio_id`s into
`impacted_portfolio_ids` and stamp that list onto every survivor before
publishing. One `_route()` call is always exactly one underlying event
(every candidate it fans out shares one `event_fingerprint` by
construction), so this is a same-call aggregation, not a new
cross-call/cross-cycle grouping mechanism — no new state, no new table
(§11's own instruction: prefer no schema change if the existing models
suffice; here they do).

```
domain change
  -> portfolio fan-out (attach_portfolio_context, unchanged)
  -> per-portfolio suppression (is_duplicate/record_emitted, unchanged, first)
  -> impacted_portfolio_ids computed from survivors only
  -> publish once per survivor (unchanged count/delivery)
  -> frontend collapses same-event_fingerprint arrivals into one entry
```

**Suppression ordering is the one genuine invariant this milestone
depends on and must never invert.** Suppression runs before grouping is
computed — a portfolio whose copy is suppressed contributes nothing to
`impacted_portfolio_ids` and never appears in it, exactly as if it were
never a candidate. Grouping a suppressed candidate in *anyway* (e.g. by
computing the group from all fan-out candidates instead of only
survivors) would leak a suppressed portfolio's identity into a
notification it was never supposed to produce one for, and would let
grouping silently widen what suppression already correctly narrowed.
Verified: `test_per_portfolio_suppression_remains_independent_after_grouping`.

**Delivery is unchanged — still one broadcast per surviving portfolio.**
`EventPublisher`'s `correlation_id` (`portfolio_id or entity_id`) is what
lets a client subscribe narrowly to one portfolio's events
(`SubscriptionRegistry.matches`, an exact-string match — §10). A single
collapsed broadcast could only carry one `correlation_id` and would
silently stop reaching a client narrowly subscribed to any of the
*other* impacted portfolios — this codebase's frontend never actually
uses narrow correlation-id subscriptions today, but the backend
capability is real, tested infrastructure that a future client could,
and this milestone does not regress it. Collapsing three network-visible
frames into one visible notification is therefore done client-side.

**Authorization.** This codebase has no per-user watchlist ownership
model (§10, unchanged, not introduced here) — "authorized" for the
grouped payload means two things, both already true by construction,
neither a new access-control mechanism: (1) the existing WS event-type
permission gate, unchanged; (2) a portfolio only ever appears in
`impacted_portfolio_ids` if it was genuinely found impacted
(`find_impacted_portfolios`) *and* independently survived its own
suppression check — never "every portfolio in the system." Verified:
`test_portfolio_tracking_a_different_ticker_never_appears_in_the_impacted_list`.

**Frontend.** `DetectedChange.impacted_portfolio_ids` (additive) travels
identically on every frame in a group. `realtime-notification-store.ts`'s
`addEntry` became a group-aware upsert: an incoming entry carrying a
`groupKey` (`event_fingerprint`, when present) replaces any existing
entry with the same key — moved to the top, `affectedPortfolioCount`
refreshed, prior `read` state preserved — instead of appending a new
row; an entry with no `groupKey` (every non-grouped domain — alerts,
backtests, ...) keeps the exact pre-v1.2 unconditional-prepend behavior.
`use-realtime-sync.ts` checks whether a `groupKey` was already present
*before* upserting, and skips the toast/desktop-notification side
channels (not the Notification Center upsert itself) for a later arrival
in an already-seen group — the three per-portfolio WS frames a real Dell
event produces still arrive, but only the first produces a toast/desktop
notification, and the Notification Center always shows exactly one row
reading e.g. "Dell Technologies Inc.: significant market move · ...
Affected: 3 portfolios."

**Live-verified** (2026-08-21, real data, no fabrication): this
deployment's own live watchlists already had Dell tracked by 3 real
portfolios (`M14 Live Acceptance`, `M15 Live Risk Test`, `M16 Live CI
Test`) — no synthetic scenario needed. A real `scripts/run_ingestion.py`
run fetched 5 genuinely new Dell articles from the live RSS feed; the
next cycle's `NEWS:dell:count:25` event correctly fanned out to exactly
those 3 real portfolio ids (3 WS-level frames, all sharing one
`event_fingerprint`/one `impacted_portfolio_ids` list) — collapsing to
one Notification Center entry client-side. `SanDisk` (2 real tracking
watchlists) produced a second, independent 2-portfolio group in the same
cycle, confirming distinct entities never conflate. `events_suppressed:
2` in the same cycle confirms suppression remained fully active
alongside grouping.

## 20. v1.2 Priority 3 — Portfolio Decision Digest

Multiple *different* decision-domain changes (Risk/Recommendation/
Strategy/Signal) for the *same* portfolio, arriving close together, used
to surface as separate Notification Center entries — e.g. a real Risk
severity change followed a minute later by a real Recommendation change
for the same portfolio produced two rows with no indication they were
related. This milestone folds them into one digest entry, entirely
client-side — **no backend change was required or made**: every field a
digest needs (`domain`, `label`, `previous_value`, `current_value`,
`priority`, `summary`, `event_fingerprint`, `portfolio_id`) already
exists on `PORTFOLIO_INTELLIGENCE_CHANGED`'s own `DetectedChange`
payload (§9), unchanged since Milestone 15.

**Digest key: `portfolio_id` + a time window, never `event_fingerprint`
alone.** §19's own grouping key (`event_fingerprint`) answers "is this
the same underlying event, routed to a different portfolio?" — a
different axis entirely from this milestone's "are these different
events, for the same portfolio, close together in time?" Two different
domains (Risk, Recommendation) for one portfolio have two different
`event_fingerprint`s and must never be conflated by §19's own mechanism
— they only ever combine here, one layer up.

**Window: `DECISION_DIGEST_WINDOW_MS` (5 minutes), explicit and named**
(`frontend/src/store/realtime-notification-store.ts`) — not a hardcoded
magic number scattered through the logic. Anchored to the digest's
*first* contained change (`digest.windowStart`, fixed for the digest's
lifetime) — a later change extends the digest's visible content but
never resets the window clock, so a digest cannot grow forever by
perpetually deferring its own expiry.

**Interaction with §19 — the required ordering, not undone:**

```
domain event
  -> per-portfolio authorization/suppression (§8, backend, unchanged)
  -> Priority-2 same-event_fingerprint grouping (§19, backend + client, unchanged)
  -> per-portfolio decision digest (this section, client-only, new)
  -> Notification Center
```

By the time an event reaches `addEntry`, §19's own server-side fan-out
and per-candidate suppression have already happened, and the client has
already received one broadcast per surviving portfolio — this section
never touches that. What it adds is purely at the *store* layer: a
`"decisions"`-domain entry for a known portfolio (`entry.pendingDigestChange`,
built once in `toNotificationEntry`) folds into an existing same-portfolio
digest still inside its window, or starts a new one-change digest
otherwise. A redelivery of the exact same `event_fingerprint` (the same
scenario §19 already handles for cross-portfolio fan-out) replaces its
own entry within the digest's `changes` array rather than duplicating.
Every non-`"decisions"` domain (alerts, backtests, market, news,
health, ...) is entirely unaffected — `addEntry` only takes the digest
path when `pendingDigestChange` is present.

**Priority**: the highest tier among the digest's own contained changes
(`LOW < MEDIUM < HIGH < CRITICAL` — the same ordering `PriorityBadge`'s
own styling table already implies, not a new hierarchy). Recomputed on
every fold-in, never frozen at the digest's creation.

**Preserved detail, never a lossy merge.** Each contained change keeps
its own `domain`/`label`/`previous_value`/`current_value`/`priority`/
`summary`/`occurredAt`/`event_fingerprint` inside `digest.changes` — the
digest's own `title`/`summary` are a compact roll-up ("N decision
changes affecting {portfolio}", "Risk: LOW → HIGH; Recommendation: HOLD
→ BUY") for the collapsed list view, but nothing is discarded: the
Notification Center card lists each change on its own line once a
digest holds more than one (`notification-center-page.tsx`, additive —
the card itself was not redesigned). A digest of exactly one change
looks identical to a pre-v1.2 single decision entry — no visible change
for the common case.

**Restart semantics.** Digest state lives only in `realtime-notification-store.ts`
— the same session-only, never-persisted design every Notification
Center entry already has (§11, unchanged since Milestone 15: no WS
message replay exists either, so a reconnect after a reload has no
history to rebuild from regardless). An active digest's window resets
along with the rest of the browser session on reload — a change that
would have folded into the pre-reload digest instead starts a fresh one
post-reload. No PostgreSQL schema was added; genuinely not required —
one `_route()`-call's worth of data already carries everything, and
digesting spans only a live client session, not something a restart
needs to recover.

**Live-verified** (2026-08-21, real data, no fabrication): this
deployment's own portfolio `M14 Live Acceptance` already had two real,
different-domain, already-stored results 36 seconds apart — a real Risk
assessment (`HIGH` severity, generated 2026-08-14T18:54:11Z) and a real
Recommendation result (`DELL`, `AVOID`, score `0.0`, generated
2026-08-14T18:53:35Z), both read directly from the live database. Fed
through the real, unmodified `toNotificationEntry`/`addEntry` code (no
synthetic evidence generated — a live-generated third Strategy change
was considered and deliberately not created, since doing so would have
required injecting synthetic screening evidence into the production
database, itself a form of fabrication this milestone's own instruction
prohibits): the result was exactly one digest entry, `digest.changes`
length 2, title `"2 decision changes affecting M14 Live Acceptance"`,
priority `HIGH` (correctly the max of `HIGH`/`MEDIUM`), and
`entityRef.portfolioId` correctly pointing at the real portfolio.

## 17. Known limitations

- **Risk/Recommendation changes require something else to have already
  computed a new result** — this cycle never triggers new computation
  itself (§16); a portfolio whose risk/recommendations are never
  recomputed by any pathway will never produce a decision-context
  change, regardless of how long Continuous Intelligence runs.
- **No per-user watchlist ownership / no "notify everyone" mechanism**
  — §10; scope is enforced by permission + `correlation_id` only, the
  same model the rest of this WS framework already uses.
- **State/suppression/locking are in-memory-only, and thus restart-unsafe,
  when no PostgreSQL repository is reachable at startup** (Milestone 16) —
  see `CONTINUOUS_INTELLIGENCE_PERSISTENCE.md` for the full persistence
  design, restart semantics, and single-process boundaries that remain
  even with Postgres.
- Every Milestone 13/14 market-data limitation (single provider, no
  fundamentals, in-memory snapshot cache, no persisted history) applies
  unchanged — this milestone adds no new provider, only real-history-driven
  health reporting on the existing one (Milestone 16 §10).
- **Cross-portfolio notification grouping (v1.2 Priority 2, §19) is
  client-side presentation only, not a reduction in WS network traffic.**
  One broadcast per surviving portfolio still goes out — deliberately,
  to preserve narrow `correlation_id` subscription delivery (§19's own
  reasoning) — a client that skipped the Notification Center layer
  entirely and read raw WS frames directly would still see N frames for
  one event, not one. True server-side traffic reduction would require
  either a multi-value `correlation_id` (a `Subscription`/matching-model
  change) or a distributed fan-out layer, both out of scope (no
  WebSocket transport redesign, per this milestone's own instruction).
- **No true magnitude-proportional grouping summary** — a grouped
  notification's `summary` is the underlying `DetectedChange.summary`
  verbatim (e.g. "Dell moved down 11.42%..."), with "Affected: N
  portfolios" appended; it does not attempt to summarize *how* the event
  affects each portfolio differently (e.g. position size, existing
  holdings) — no such per-portfolio detail exists anywhere in this
  codebase to summarize (`docs/release/KNOWN_LIMITATIONS.md`'s own
  "Valuation is permanently VALUATION_UNAVAILABLE" — Milestone 14).
- **Portfolio Decision Digest (v1.2 Priority 3, §20) state is
  session-only, like every other Notification Center entry** — an active
  digest's window resets on reload/reconnect; a change that would have
  extended a pre-reload digest instead starts a new one after. No
  PostgreSQL schema was added for it, deliberately (§20's own reasoning).
- ~~The digest window (5 minutes, `DECISION_DIGEST_WINDOW_MS`) is not
  user-configurable~~ — **superseded by v1.2 Priority 4 (§21)**: the
  window is now configurable, 1-30 minutes, via Workspace Settings.
  `DECISION_DIGEST_WINDOW_MS` remains as the literal default value.
- **Cross-portfolio grouping and the toast pop-up are each individually
  presentation-only user preferences as of v1.2 Priority 4 (§21)** —
  neither preference can be used to infer anything about server-side
  suppression, authorization, or delivery; both default to the §19/§16
  behavior this document already describes.

## 21. v1.2 Priority 4: Notification & Intelligence Preferences

Makes 3 presentation behaviors already described in this document
user-configurable, entirely client-side, reusing Milestone 8's existing
`preferences-store.ts`/`preferences-io.ts` machinery — **no backend
change, no WebSocket protocol change, no new persistence mechanism, no
new settings page.** See `docs/frontend/MILESTONE_8.md` §8 for the full
field list and UI. In terms of this document's own sections:

- **§19 (cross-portfolio grouping)** is now gated by
  `notifications.groupCrossPortfolioNotifications` (default `true`).
  `false` makes `addEntry` treat every arrival as ungrouped (one
  Notification Center row per portfolio, mirroring pre-§19 behavior) —
  the backend's one-broadcast-per-surviving-portfolio behavior (§19's own
  "not a reduction in WS network traffic" limitation, still true) is
  entirely unchanged either way.
- **§20 (decision digest)** now reads its fold window from
  `notifications.decisionDigestWindowMinutes` (1-30, default 5) instead
  of the fixed `DECISION_DIGEST_WINDOW_MS`. Locked into each digest's own
  `windowMs` field at creation (its first change) — §20's own "anchored
  to the digest's first contained change" invariant is preserved exactly,
  now extended to cover the window's *length* as well as its *start*: a
  setting change mid-digest affects only digests created after the
  change, never a digest already open.
- **The realtime toast** (not part of this document's own domain, but
  fired from the same `use-realtime-sync.ts` dispatch point §19/§20
  describe) is now gated by `notifications.showRealtimeToasts` (default
  `true`) — gates only the toast; Notification Center insertion, unread
  state, and cache invalidation are unaffected, and desktop notifications
  keep their pre-existing, separate `desktopNotificationsEnabled` toggle.
