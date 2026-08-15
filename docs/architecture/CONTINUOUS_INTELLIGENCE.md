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
