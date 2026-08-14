# Live Market Data & Price Intelligence

**Milestone 13 — post-v1.0.0 / v1.1 candidate.** Extends Milestone 12's
canonical entity model with real market-state information; v1.0.0's own
scope, status, and sign-off are unchanged by this document. See
`docs/release/UPGRADE_POLICY.md`'s versioning rules for what a v1.1
candidate capability means in this repository.

## 1. Architecture — nothing replaced, one real provider added

Milestone 13 inspected `app/market_data/` and `app/providers/market_data/`
first (per its own §1 instruction) and found a complete, already-designed
abstraction with exactly one gap: `MarketDataProvider` (the abstract
contract), `NormalizationService` (provider-agnostic normalization), and
every domain model (`MarketQuote`, `CompanyProfile`, `HistoricalSeries`,
`ProviderCapabilities`, `ProviderHealth`, …) already existed — only
`MockMarketDataProvider` (deterministic, in-memory) implemented the
contract. No business service in the codebase called `MarketDataProvider`
at all before this milestone (verified by inspection) — a genuinely
greenfield integration, not a change to any existing consumer's contract.

```
YahooFinanceProvider (real HTTP, NEW)  <-- implements -->  MarketDataProvider (existing ABC)
        |
        v
MarketSnapshotService (NEW)  --uses-->  EntityResolutionService.get_by_entity_id() (Milestone 12)
        |                                        (ticker/exchange/currency mapping)
        v
InMemoryMarketSnapshotCache (NEW, TTL-bounded)
        |
        +--> CompanyResearchAgent (Research integration, additive)
        +--> MarketDataRefreshWorkflow (scheduled refresh, existing Scheduler)
        +--> scripts/run_market_data_refresh.py (operational trigger)
```

Every new piece is additive: no existing model, provider interface, or
consumer contract was changed in a breaking way.

## 2. Provider selected

**Yahoo Finance's public chart endpoint**
(`https://query1.finance.yahoo.com/v8/finance/chart/{ticker}`) —
`app/providers/market_data/yahoo.py::YahooFinanceProvider`.

Chosen over the alternatives evaluated during implementation:

- **Stooq** (`stooq.com`) — historically a common free, no-key CSV quote
  source, but its `/q/l/` endpoint now 404s and its historical-download
  endpoint serves a JavaScript proof-of-work bot challenge instead of
  data. Not viable today.
- **Alpha Vantage / Finnhub / Twelve Data** — all require a signed-up API
  key. Rejected as the *first* provider per §2's "choose the simplest
  production-usable provider" instruction — Yahoo Finance needs no
  credential at all, so live Docker acceptance (§17) and any future
  deployment need zero setup friction. A key-requiring provider remains
  a reasonable *additional* provider for a future milestone if Yahoo's
  endpoint ever becomes unreliable (§16, known limitations).

Verified live against real symbols (`AAPL`, `DELL`) during
implementation — real price, previous close, currency, exchange, and
timestamp were returned and correctly normalized.

No API key, no signup, no secret of any kind is required or stored.

## 3. Provider capabilities

`YahooFinanceProvider.capabilities()` reports exactly what the chart
endpoint can back with real data — never a capability it can't honor:

| Capability | Supported | Why |
|---|---|---|
| `supports_quotes` | ✅ | `meta.regularMarketPrice` etc. |
| `supports_history` | ✅ | The same endpoint, queried with a `range`/`interval`, returns OHLCV bars |
| `supports_intraday` | ✅ | `1m`/`5m`/`15m`/`30m`/`60m` intervals all map to real Yahoo interval tokens |
| `supports_fundamentals` | ❌ | Not present in this endpoint's response |
| `supports_dividends` | ❌ | Not present |
| `supports_search` | ❌ | Not present |
| `supports_batch` | ❌ | No true multi-symbol request — `get_quotes()` loops `get_quote()` per ticker internally (concurrency-bounded), matching the ABC's own documented allowance for a provider without a real batch call |

Every abstract method this endpoint cannot back
(`get_company_profile`, `get_fundamentals`, `get_financial_ratios`,
`get_market_cap`, `get_earnings`, `get_dividends`, `search_symbol`)
raises `ProviderConfigurationError` explicitly, rather than returning an
empty/zeroed model — returning a fabricated-looking "nothing to report"
would misrepresent "not supported" exactly as much as a wrong number
would (this codebase's "never fabricate" rule, carried over from
Milestones 11-12).

## 4. Configuration

All in `AppSettings` (`app/bootstrap.py`), documented in `.env.example`:

| Setting | Default | Meaning |
|---|---|---|
| `MARKET_DATA_PROVIDER` | `mock` | `mock` \| `yahoo_finance`. Unlike `ENTITY_RESOLUTION_ENABLED`, this defaults to the safe/inert option — a real provider is a new outbound network call surface, matching `INGESTION_ENABLED`'s own "don't silently change an existing deployment's behavior" reasoning. |
| `MARKET_DATA_TIMEOUT_SECONDS` | `10.0` | Per-request timeout. |
| `MARKET_DATA_RETRY_ATTEMPTS` | `1` | Retries per quote request (same fixed-backoff technique `RSSProvider` already uses). |
| `MARKET_DATA_RETRY_BACKOFF_SECONDS` | `1.0` | |
| `MARKET_DATA_CACHE_TTL_SECONDS` | `60.0` | How long a fetched snapshot is served from cache before being STALE. |
| `MARKET_DATA_ENABLED` | `false` | Gates the *scheduled* refresh job only — independent of which provider is selected. |
| `MARKET_DATA_REFRESH_INTERVAL_SECONDS` | `3600.0` | |

An unrecognized `MARKET_DATA_PROVIDER` value, or a real-provider
construction failure, degrades to `MockMarketDataProvider` (logged) — the
same "never crash startup over bad optional config" shape every other
dependency in `app.bootstrap` already uses.

## 5. Entity / security mapping (Milestone 12 integration)

`EntityResolutionService` gained two small, additive accessors (no change
to the canonical `CompanyReference` model itself):

- `get_by_entity_id(entity_id) -> CompanyReference | None` — the mapping
  `MarketSnapshotService` uses to go from a canonical entity to its
  `.ticker`/`.exchange`/`.currency`. Unknown id -> `None`, never guessed.
- `list_references() -> tuple[CompanyReference, ...]` — enumerates every
  known canonical entity, used by `MarketDataRefreshWorkflow` to know
  what to refresh.

An entity with no ticker (or no entity at all) is reported as
`MarketSnapshotStatus.ENTITY_NOT_MAPPED` — the display *name* is never
used as a lookup key on its own.

## 6. Normalized market-data model

`app/services/market_snapshot/models.py::MarketSnapshot` — deliberately
distinct from the pre-existing `app.market_data.models.MarketQuote` (the
raw provider-shaped normalized quote): this model additionally answers
*which canonical entity*, *which provider*, and separates *when this was
quoted* (`quoted_at`, the provider's own timestamp) from *when this
service fetched/cached it* (`fetched_at`) — the exact distinction §19
("data quality") requires every displayed price be able to answer.

| Field | |
|---|---|
| `entity_id`, `canonical_name` | From Milestone 12's `CompanyReference` |
| `ticker`, `exchange`, `currency` | |
| `price`, `previous_close`, `change`, `change_percent` | |
| `day_high`, `day_low`, `volume` | When the provider supplies them |
| `quoted_at` | The provider's own quote timestamp — always timezone-aware |
| `fetched_at` | This service's own cache-write timestamp — always timezone-aware |
| `provider` | e.g. `"Yahoo Finance"` |
| `trading_status` | Provider's own market-open/closed signal, when available |

`MarketSnapshotResult` (what every caller actually receives) wraps this
with an explicit `status` (`MarketSnapshotStatus`, §7) and `reason` —
never raised for an ordinary outcome, so a caller never needs to
distinguish "no data" from "an exception" via try/except.

## 7. Cache & freshness

`app/services/market_snapshot/cache.py::InMemoryMarketSnapshotCache` — not
a distributed/Redis cache (per §6's own "don't invent distributed
infrastructure the architecture doesn't call for" instruction — no
existing infrastructure in this codebase needed one for this purpose,
same judgment already applied to `InMemoryResultStore`/
`InMemoryMetricsRecorder`). Process-local, lost on restart — acceptable
for a bounded, short-TTL quote cache.

- **Deterministic key**: `entity_id` (never the display name, never the
  ticker alone — two entities could theoretically share a ticker string
  across exchanges).
- **Bounded TTL**: `MARKET_DATA_CACHE_TTL_SECONDS`.
- **Freshness is always explicit** — every result carries exactly one of:

  | Status | Meaning |
  |---|---|
  | `FRESH` | Fetched just now, or served from cache within the TTL window |
  | `STALE` | The provider failed, but a past-TTL cached value exists — served explicitly marked stale, **never** presented as current |
  | `UNAVAILABLE` / the specific failure status (§8) | No usable cached value exists at all |

  Freshness compares against `fetched_at` (when *this service* cached
  it), never `quoted_at` (the provider's own timestamp, which can
  legitimately be older even for a freshly-fetched quote — e.g. a quote
  fetched right after market close still carries the last trade's own
  timestamp).

## 8. Error handling

Every distinct outcome §7 of the milestone's own spec asks for is a named
`MarketSnapshotStatus` member, mapped from the specific provider
exception (`app/providers/exceptions.py`) that produced it:

| Provider exception | Status |
|---|---|
| Entity has no ticker / doesn't resolve | `ENTITY_NOT_MAPPED` |
| `ProviderTimeoutError` | `PROVIDER_TIMEOUT` |
| `ProviderRateLimitError` (HTTP 429) | `RATE_LIMITED` |
| `ProviderNoDataError` (new, Milestone 13 — unknown/delisted ticker) | `NO_DATA` |
| `ProviderResponseError` (malformed payload) | `INVALID_RESPONSE` |
| `ProviderConnectionError` | `PROVIDER_UNAVAILABLE` |
| Any other `ProviderError` | `UNAVAILABLE` |

`ProviderNoDataError` is a new addition to the shared
`app/providers/exceptions.py` hierarchy — distinct from
`ProviderResponseError` (the response itself was malformed) and from a
connection/timeout failure, so "no data exists" is never confused with
"provider failed," exactly as §7 requires. Reusable by any future
provider, not Yahoo-specific.

`MarketSnapshotService.get_snapshot()`/`get_snapshots()` never raise for
any of these — always a `MarketSnapshotResult` with an explicit status.
`get_snapshots()` additionally catches any genuinely unexpected exception
(not just the modeled `ProviderError` subclasses) and converts it to
`UNAVAILABLE`, so one bad symbol can never fail an entire batch (§12).

## 9. Scheduler

`MarketDataRefreshWorkflow` (`app/workflows/market_data_refresh/`) —
implements the same `WorkflowProtocol` (`execute(context) -> result`)
`MorningPipeline` (Milestone 11) already does, registered with the
existing `WorkflowEngine`/`Scheduler` infrastructure via
`register_market_data_schedule` — the identical pattern
`register_ingestion_schedule` established. Refreshes every canonical
entity `EntityResolutionService.list_references()` reports, via
`MarketSnapshotService.get_snapshots()` — the *same* service (and cache)
Research uses, so a scheduled refresh keeps the cache Research reads from
warm, rather than maintaining a second, separate cache.

Gated by `MARKET_DATA_ENABLED` (default `false`) — not registered at all
if `entity_resolution_service` is unavailable (nothing to enumerate).

## 10. Operational trigger

`scripts/run_market_data_refresh.py` — container-exec only, mirrors
`scripts/run_ingestion.py`/`scripts/run_entity_backfill.py` exactly:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec backend python scripts/run_market_data_refresh.py
```

Prints a JSON summary (entities requested, fresh/stale/unavailable
counts, and the per-entity status/reason for anything not `FRESH` — so a
specific stale or unavailable symbol is individually identifiable).
Exits `1` if the workflow isn't registered or is disabled
(`MARKET_DATA_ENABLED` is not `true`). No unauthenticated HTTP endpoint
was added for this — the frozen `/api/v1` surface is unchanged.

## 11. Research / Portfolio integration

**Research** (`CompanyResearchAgent`): an optional
`market_snapshot_service` constructor parameter (default `None` —
identical pre-Milestone-13 behavior when omitted). When provided, the
*same* resolved entity Milestone 12 already computes
(`lookup_by_name_or_ticker`) is reused — no second, separate resolution
— to fetch a snapshot, attached to `CompanyResearchReport.market_snapshot`
(reusing `MarketSnapshotResult` directly, not a second report-local
model). A market-data failure degrades `.status`, it never fails Research
itself, and evidence/news sections are completely unaffected by its
presence.

**Portfolio / Risk / Recommendation / Strategy / Historical Analysis**:
inspected per §10's own instruction — **no integration added as of
Milestone 13**. No existing contract in any of these consumers explicitly
expected market data at the time (confirmed by inspection: none of them
called `MarketDataProvider` at all). Per §10's explicit conditional
instruction ("integrate only where the existing contract explicitly
expects market data... do not change existing formulas simply to consume
new data"), forcing an integration here would have meant changing
formulas never designed to consume it. **Deliberately deferred** at the
time.

**Resolved post-v1.0 (Milestone 14)**: Portfolio, Recommendations,
Strategy, Signals, and Risk are now market-aware — see
`docs/architecture/PORTFOLIO_INTELLIGENCE.md` for the full design. Risk's
own scoring *formulas* remain exactly as documented above (still no
market data feeds `MARKET_CAP`/`VOLATILITY`/`LIQUIDITY`) — Milestone 14
added a purely informational `market_data_coverage` field, never a
formula change. Historical Analysis / Backtesting remain unintegrated —
still no existing contract there expects market data.

## 12. Security

- **No credential required.** Yahoo Finance's chart endpoint needs no API
  key — nothing to keep outside source control for this provider. The
  provider abstraction itself imposes no constraint against a future
  key-requiring provider being added the same way `AnthropicSettings`
  already handles a real secret (env-var only, never logged).
- **No secrets in logs.** Every structured log line
  (`yahoo_finance_request_retry`/`_failed`, `market_snapshot_provider_failed`,
  `market_data_refresh_*`) logs only ticker/entity ids, status values, and
  exception messages — never a request header or credential.
- **External data is untrusted.** Every field read from the chart
  response is defensively checked (`_parse_chart_response`) before use;
  a malformed/unexpected shape raises `ProviderResponseError` rather than
  propagating a raw `KeyError`/`TypeError`.
- **Configuration-controlled URL.** `YahooFinanceProviderConfig.base_url`
  is a fixed, operator-configured value — no endpoint in this codebase
  accepts a caller-supplied URL to fetch (no SSRF surface, same reasoning
  already documented for RSS feed URLs).
- **Timeouts on every request** — `MARKET_DATA_TIMEOUT_SECONDS`, applied
  per attempt.
- **No arbitrary user-controlled fetch** — tickers passed to `get_quote`
  come only from the canonical `CompanyReference` reference set (Milestone
  12) or an operator-triggered refresh, never directly from unauthenticated
  request input.

## 13. Rate limits

Yahoo Finance's public chart endpoint publishes no documented rate limit
for this usage pattern. `YahooFinanceProvider` treats HTTP 429 as
`ProviderRateLimitError` (mapped to `MarketSnapshotStatus.RATE_LIMITED`)
if the vendor ever returns one. `get_quotes()`/`MarketSnapshotService
.get_snapshots()` both bound concurrent in-flight requests
(`_MAX_CONCURRENT_REQUESTS` / `DEFAULT_MAX_CONCURRENCY`, both `5`) as a
conservative, configuration-independent guard against an accidental
request storm — not a measured vendor limit, since none is published.

## 14. Known limitations

- **Single real provider, no fallback.** If Yahoo Finance's chart
  endpoint becomes unavailable or changes shape, there is no automatic
  fallback to a second vendor — `MARKET_DATA_PROVIDER` can be switched
  back to `mock`, or a new provider added following the same
  `MarketDataProvider` contract, but no such switch happens automatically
  today.
- **No fundamentals/dividends/earnings/search from the real provider** —
  only quotes and historical OHLCV are backed by real data; the other
  `MarketDataProvider` methods raise `ProviderConfigurationError` when
  `yahoo_finance` is selected (§3).
- **In-memory cache only** — lost on restart, not shared across replicas
  running multiple backend instances (same characteristic already
  documented for the Milestone 11 scheduler / Milestone 12 backfill).
- ~~**No Portfolio/Risk/Recommendation integration** — deliberately
  deferred (§11).~~ **Resolved post-v1.0 (Milestone 14)** for Portfolio,
  Recommendations, Strategy, Signals, and Risk (coverage-tracking only,
  not a formula change) — see
  `docs/architecture/PORTFOLIO_INTELLIGENCE.md`. Historical
  Analysis/Backtesting remain unintegrated.
- **No persisted market-snapshot history** — `MarketSnapshotService`
  caches the *latest* snapshot per entity only; no time-series of past
  snapshots is stored anywhere.
