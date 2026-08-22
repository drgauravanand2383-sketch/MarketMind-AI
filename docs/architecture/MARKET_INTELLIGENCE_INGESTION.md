# Market Intelligence & News Ingestion Pipeline

**Milestone 11 — post-v1.0.0.** This is a new capability, not part of the
frozen v1.0.0 release (`docs/release/API_CONTRACT_V1.md`); v1.0.0's own
scope, status, and sign-off are unchanged by this document. See
`docs/release/UPGRADE_POLICY.md`'s versioning rules for what a v1.1
candidate capability means in this repository.

**Related, independent capabilities built on top of this pipeline**:
Milestone 12 (`docs/architecture/ENTITY_RESOLUTION.md`) resolves each
ingested article to a canonical company; Milestone 13
(`docs/architecture/MARKET_DATA_ARCHITECTURE.md`) adds real market-price
data for those same canonical companies. Neither changed anything
described in this document — this pipeline's own ingestion/dedup/
provenance behavior is unmodified.

## 1. Root cause this milestone fixes

v1.0.0's Research UI (`GET /api/v1/research/*`) always returned
`NO_DATA`/"Unmatched" for every company, in every environment — not a
company-resolution bug, but because `knowledge_records` was empty
everywhere: the ingestion pipeline that would populate it
(`MorningPipeline`) was fully built and tested (Sprint 35) but never
registered anywhere in `app/bootstrap.py`, and no concrete
`BaseEmbeddingProvider` existed for it to depend on. See the
acceptance-diagnosis session that produced this milestone for the full
investigation; the short version: `app/bootstrap.py`'s own module
docstring said so explicitly, prior to this milestone.

## 2. Architecture — nothing new invented

Every component below already existed, already tested, before this
milestone — the only new code is `LocalEmbeddingProvider`
(§3), the bootstrap wiring that connects the existing pieces (§4-6), one
operational trigger script (§7), and a handful of completions to already-
existing components (idempotent upsert, retry, deterministic ids — §8).

```
RSSProvider (real HTTP + feedparser)
        |  (via NewsCollectorAgent's own ProviderRegistry)
        v
NewsCollectorAgent  --(NewsCollectionResult)-->  KnowledgeIngestionService
        |                                              |  (Milestone 12: optionally
        |                                              |   calls EntityResolutionService
        |                                              |   per item — see
        |                                              |   docs/architecture/ENTITY_RESOLUTION.md)
        |                                    (IngestionBatch: VectorDocuments
        |                                     + RelationalRecords + rejects)
        v                                              v
MorningPipeline  <---------------------------  EmbeddingService (chunking)
        |                                              |
        |                                              v
        |                                   LocalEmbeddingProvider (NEW)
        |                                              |
        v                                              v
ChromaKnowledgeRepository.save_batch(ingestion_batch, embedding_batch)
        |
        v
KnowledgeHub.query(company_name)  <-- already used by CompanyResearchAgent
```

`MorningPipeline` (`app/workflows/morning_pipeline/pipeline.py`) is the
orchestrator — 8 explicit, independently-testable stages: `news_collector
-> knowledge_ingestion -> embedding_service -> embedding_provider ->
knowledge_repository -> evidence_engine -> market_intelligence_engine ->
relationship_engine`. Halts on the first stage that raises; every stage
before that point is preserved in the returned `PipelineResult`. This
milestone did not change that stage sequence or its halt semantics.

## 3. Embedding provider

`app/providers/embedding/local.py::LocalEmbeddingProvider` — the first
concrete `BaseEmbeddingProvider` implementation. Backed by ChromaDB's own
bundled `DefaultEmbeddingFunction` (a local, CPU-only
`all-MiniLM-L6-v2` ONNX sentence-transformer model) — `chromadb` is
already a project dependency (used for storage), so this introduces **no
new external service, no API key, and no new package**. The model is
downloaded once to a local cache (`~/.cache/chroma/onnx_models/` inside
the backend container) on first real use; every call after that is local
CPU inference, deterministic for the same input text.

`EMBEDDING_PROVIDER` (default `"local"`) selects the concrete
implementation in `app/bootstrap.py::build_embedding_provider` — never
hardcoded into `MorningPipeline`, which only depends on the
`BaseEmbeddingProvider` abstraction. An unrecognized value degrades to
`None` (logged), the same "not configured" shape every other optional
bootstrap dependency already uses.

The embedding function itself is constructed lazily (first actual call,
not at provider construction) and injectable
(`embedding_function_factory`) — production code omits it and gets the
real model; every test injects a cheap fake callable, so no test in this
codebase downloads a model or touches the network.

**Known architectural quirk, not fixed by this milestone**:
`ChromaKnowledgeRepository.save_batch()` (pre-existing, unchanged) does
not actually consume the vectors `LocalEmbeddingProvider` computes — it
passes raw text to `collection.upsert()`, and the ChromaDB collection's
own configured embedding function (the same `DefaultEmbeddingFunction`,
since `app.bootstrap.build_knowledge_repository` never overrides it)
computes the vector actually stored. `MorningPipeline`'s own Stage 4
(`embedding_provider`) still runs, still must succeed, and its
`EmbeddingResult` still feeds this milestone's observability counts — but
the vector it computes and the vector ChromaDB stores are computed twice,
independently, by the same underlying model. Changing
`ChromaKnowledgeRepository` to consume precomputed vectors would be a
repository-behavior change beyond this milestone's "complete the existing
pipeline, don't redesign it" scope — left for a future milestone.

## 4. RSS / news ingestion

`RSSProvider` (`app/providers/rss/provider.py`) already existed as a
real, unmocked HTTP+`feedparser` client — this milestone completed three
gaps in it:

- **Retry policy**: `ProviderConfig.retry_attempts` existed but was
  never actually implemented. `_fetch_one` now retries a failed feed
  fetch up to `retry_attempts` times (default 1, i.e. one retry) with a
  fixed backoff (`RSSProviderConfig.retry_backoff_seconds`, default 1s),
  isolated per feed URL — one feed exhausting its retries never affects
  any other configured feed.
- **Redirects**: `httpx.AsyncClient` does not follow redirects by
  default; many real-world feed URLs permanently redirect to a new
  address (a provider migrating infrastructure, a CDN change). Added
  `follow_redirects=True` — this is standard HTTP-client behavior for
  fetching a feed at its configured address, not scraping a different
  site (see §11, Security).
- **Deterministic identity for feeds without a `<guid>`**:
  `app/agents/news_collector/normalizer.py::_entry_id` now falls back to
  a stable id derived from the entry's canonical URL
  (`sha256(url)`-based) when the feed provides no `<guid>`/`<id>` at all
  — common for feeds that only ever set `<link>`. Same URL always
  produces the same id; an entry with neither a guid nor a link still
  correctly has no derivable identity and is rejected
  (`RejectionReason.MISSING_ID`) rather than assigned a made-up one.

`NewsCollectorAgent` (unchanged) already isolated provider-level
failures; `KnowledgeIngestionService` (unchanged) already validated/
deduplicated within one ingestion batch (missing id, empty content,
duplicate id within the same run).

## 5. Deduplication & idempotency

Two layers, both pre-existing except the second:

1. **Within one ingestion run**: `KnowledgeIngestionService._validate()`
   (unchanged) rejects a second occurrence of the same id within the same
   `NewsCollectionResult` — `RejectionReason.DUPLICATE_ID`.
2. **Across separate ingestion runs**: `ChromaKnowledgeRepository
   .save_batch()` now calls `collection.upsert(...)`, not `.add(...)`.
   `add` errors/rejects on an id ChromaDB already has stored; `upsert`
   inserts-or-replaces atomically. Combined with deterministic record
   identity (§4), the same article seen again on a later scheduled run —
   still present in the feed's most recent entries, or its title/summary
   was edited — replaces the existing record in place rather than
   erroring or creating a duplicate. Verified live: two consecutive runs
   against the same real feed produced the same 10-record collection
   count both times (§14 of the implementing session's own report).

## 6. Knowledge record provenance

Every ingested record's metadata (`VectorDocument.metadata`, prepared in
`KnowledgeIngestionService._to_vector_document`) answers:

| Question | Field |
|---|---|
| Where did this come from? | `url`, `source_provider_id` |
| When was it published? | `published_at` |
| When was it ingested? | `ingested_at` (new — recorded once per ingestion batch) |
| What entity/topic does it relate to? | `entity_resolved` (new — always `False` at the time this milestone shipped) |

**No entity/company resolution mechanism existed anywhere in this
codebase as of this milestone.** `entity_resolved` was set to its honest
`False` state on every record rather than fabricated or silently omitted,
per this milestone's own "unmatched articles remain valid knowledge
records with an explicit unresolved state" requirement. Research's own
retrieval (`KnowledgeHub.query`, unchanged) already worked by semantic
similarity over the record's text, not a structured company tag.

**Resolved post-v1.0 (Milestone 12)**: a real Entity Resolution & Company
Intelligence layer now computes `entity_resolved` for real — see
`docs/architecture/ENTITY_RESOLUTION.md`. This document's description of
Milestone 11's own scope is left as written above (a historical record of
what shipped at the time), with this forward pointer to where the gap was
actually closed — not retroactively rewritten.

## 7. Scheduler registration

Registered via the existing `Scheduler`/`APSchedulerService`
infrastructure (Sprint 31/35, unmodified) —
`app/bootstrap.py::register_ingestion_schedule`:

- `workflow_engine.register_workflow("market_intelligence_ingestion", morning_pipeline)`
- `scheduler.register_schedule(Schedule(trigger_type=INTERVAL, enabled=INGESTION_ENABLED, interval_seconds=INGESTION_INTERVAL_SECONDS, ...))`

Both calls are skipped (logged) if `morning_pipeline` itself couldn't be
built (chromadb unreachable, or the configured embedding provider
unavailable) — nothing to register. `APSchedulerService.register_schedule`
(unchanged) already uses `id=workflow_id, replace_existing`-safe
registration, so re-registering the same schedule never creates a
duplicate APScheduler job — this milestone relies on that existing
guarantee rather than adding a new one.

`INGESTION_ENABLED=false` (the default) means the schedule is registered
but disabled — `Scheduler`'s own contract ("`enabled` gates all execution
of a schedule, not only automatic triggering") means a disabled schedule
can't fire on its interval **or** be run manually (§8) until enabled.
This is one on/off switch for the whole capability, not two independent
ones.

## 8. Operational trigger ("run now")

`backend/scripts/run_ingestion.py` — not a REST endpoint. The frozen
`/api/v1` surface is not extended for this (per this milestone's own
constraint); this mirrors the existing `alembic upgrade head` convention
already documented (`docs/release/DEPLOYMENT_GUIDE.md` §4) — a deliberate,
separate, operator-invoked step, reachable only by whoever can already
run a command inside the backend container (the same trust boundary
Alembic already relies on — never an unauthenticated network endpoint).

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec backend python scripts/run_ingestion.py
```

Bootstraps a throwaway `FastAPI` app (reusing `bootstrap_application_state`/
`shutdown_application_state` exactly as `app/main.py`'s own lifespan
does), calls `Scheduler.run_schedule("market_intelligence_ingestion")`
once, and prints a JSON summary to stdout: run id, status, providers/
articles/embeddings/persistence counts, and any failure — built from the
same `PipelineResult.final_context.agent_outputs` the pipeline's own
`ingestion_run_completed` structured log line reports (§9). Exits `1` for
"ingestion is disabled," "not registered" (dependencies unavailable), or
a failed run; `0` on success. Never prints a token, password, or any
`.env` value.

## 9. Observability

Structured log events (stdlib `logging`, `extra={}` — the same pattern
`RequestLoggingMiddleware`/`ws_message_handling_failed` already use, no
new logging framework):

| Event | Emitted by | Key fields |
|---|---|---|
| `rss_feed_fetched` / `rss_feed_fetch_failed` | `RSSProvider._fetch_one` | `feed_url`, `entry_count` / `error` |
| `ingestion_run_started` | `MorningPipeline` | `execution_id` |
| `ingestion_run_completed` | `MorningPipeline` | `providers_attempted/succeeded/failed`, `articles_fetched/deduplicated/persisted`, `embeddings_generated`, `embedding_failures`, `entity_resolved_count`, `entity_unresolved_count`, `duration_seconds` |
| `ingestion_run_failed` | `MorningPipeline` | `execution_id`, `failed_stage`, `error` |

`providers_*` summarizes at the provider level (one entry per configured
news source, e.g. `"rss"`) — the granularity `NewsCollectorAgent` exposes
upward. Per-individual-feed-URL success/failure is the
`rss_feed_fetched`/`rss_feed_fetch_failed` pair above.

## 10. Failure behavior

- One bad feed URL never aborts the run (§4, §8's provider-level
  isolation, unchanged from before this milestone).
- One failed embedding request never aborts the run —
  `BaseEmbeddingProvider.generate()` (unchanged) retries per-request and
  records a `FailedEmbeddingRequest`, never re-raising to the pipeline.
- A genuinely fatal stage failure (e.g. ChromaDB unreachable at save
  time) halts the pipeline at that stage — `PipelineResult.status =
  FAILED`, every earlier stage's metrics preserved, logged as
  `ingestion_run_failed`. This halt behavior is pre-existing
  (`MorningPipeline`, unchanged) — this milestone only added the log
  line.

## 11. Security

- **Feed URLs are configuration-only**: `RSS_FEED_URLS` is read from
  `.env`/environment at startup — no endpoint anywhere accepts a
  caller-supplied URL to fetch. There is no arbitrary-URL-fetch surface,
  public or authenticated.
- **Timeouts**: every feed fetch is bounded by
  `RSS_FEED_TIMEOUT_SECONDS` (default 10s, per attempt) — a hanging feed
  cannot hang the pipeline indefinitely.
- **SSRF**: feed URLs come only from operator-controlled configuration,
  never from user input or request data — the standard SSRF concern
  (a request forging a fetch to an internal address) does not apply here
  the way it would for a user-facing "fetch this URL" feature. Operators
  should still only configure feed URLs they trust, same as any outbound
  HTTP configuration.
- **Untrusted content**: fetched article text/titles are stored as plain
  text and only ever rendered as such (Research's existing UI, unchanged)
  — never interpreted as HTML/script, matching this codebase's existing
  no-`dangerouslySetInnerHTML` convention. `feedparser`'s own parsing is
  used as-is; malformed feed XML (`bozo=True`) is handled gracefully
  (empty entries), not passed through to any executable context.
- **Redirects**: `follow_redirects=True` (§4) only follows redirects
  `httpx` itself validates as part of the same request — it does not
  widen what's fetchable beyond the configured feed URL's actual
  resolution chain.

## 12. Known limitations (post-v1.0, not v1.0.0 regressions)

- ~~No real entity/company resolution — every knowledge record is
  `entity_resolved: False`; Research still matches purely by semantic
  similarity over article text (§6).~~ **Resolved post-v1.0 (Milestone
  12)** — see `docs/architecture/ENTITY_RESOLUTION.md`.
- `ChromaKnowledgeRepository` doesn't consume the pipeline's own computed
  embedding vectors (§3) — a duplicate-computation quirk, not a
  correctness bug, left for a future milestone.
- Relational persistence (`RelationalRecord`, `PostgresKnowledgeRepository`
  / `CompositeKnowledgeRepository`) is not wired into `app/bootstrap.py`
  — only the ChromaDB-only `ChromaKnowledgeRepository` path is active in
  this deployment, same as before this milestone.
- No dedicated market-news aggregation surface was added (see
  `docs/release/KNOWN_LIMITATIONS.md`) — Research's existing per-report
  news section is the only place ingested news surfaces in the product
  today; this was a deliberate scope decision (the milestone's own
  instructions: build one "only if the existing architecture supports it
  cleanly," and the core requirement — Research automatically benefiting
  — was already satisfied without it).
- Single-process scheduler (`APSchedulerService`, unchanged,
  `docs/release/KNOWN_LIMITATIONS.md`'s existing "`/ws` is single-process"
  note applies identically here): running multiple backend replicas means
  each replica independently schedules its own ingestion runs — no
  distributed lock. Acceptable for this milestone's scope (idempotent
  upsert makes concurrent/overlapping runs safe, just redundant), not
  fixed here.

## 13. Sources (v1.2 Priority 6 — Company-Focused News Sources & Ingestion Quality)

The second real-world pilot found Research surfacing only ~1-2
company-matched articles even for the best-covered canonical companies,
and traced the root cause to ingestion *volume/relevance*, not a
retrieval cap (`KnowledgeHub`'s own `top_k=50` was nowhere near being
hit) — the single configured feed (MarketWatch top-stories) is a
general-audience feed whose content is dominated by personal-finance
advice ("Should I dip into my 401(k)...") rather than company-specific
business news.

**Source set, extended from 1 to 10 feeds, `RSS_FEED_URLS` only (no
second config mechanism)** — every URL below was verified live (HTTP
200, real recent articles) before being added, never guessed:

| Source | URL | Category | Why |
|---|---|---|---|
| MarketWatch Top Stories | `feeds.marketwatch.com/marketwatch/topstories/` | (none — pre-existing) | Kept unchanged; still contributes genuine market context alongside the new sources. |
| Nasdaq Markets | `nasdaq.com/feed/rssoutbound?category=Markets` | Markets | Official Nasdaq category feed — general market/company news, ticker-tagged. |
| Nasdaq Stocks | `nasdaq.com/feed/rssoutbound?category=Stocks` | Stocks | Per-company stock analysis and commentary. |
| Nasdaq Technology | `nasdaq.com/feed/rssoutbound?category=Technology` | Technology | Directly relevant — most canonical companies (AAPL, MSFT, NVDA, DELL, CRM, WDAY, ...) are technology companies. |
| Nasdaq Earnings | `nasdaq.com/feed/rssoutbound?category=Earnings` | Earnings | Earnings-specific coverage — the single highest-value recurring event type for Risk/Recommendation/Decision quality. |
| Dell Technologies IR | `investors.delltechnologies.com/rss/news-releases.xml` | Company IR | Official IR feed — ground-truth company announcements, not filtered through general-media pickup. |
| Salesforce IR | `investor.salesforce.com/rss/pressrelease.aspx` | Company IR | Same reasoning; Q4 Inc.-hosted (a standard, authoritative IR platform). |
| Workday IR | `investor.workday.com/rss/pressrelease.aspx` | Company IR | Same reasoning; Q4 Inc.-hosted. |
| Reddit IR | `investor.redditinc.com/rss/pressrelease.aspx` | Company IR | Same reasoning; Q4 Inc.-hosted. |
| Sandisk IR | `investor.sandisk.com/rss/news-releases.xml` | Company IR | Same reasoning. |

**Why these 5 companies got a dedicated IR feed and the other 7 canonical
companies (AAPL, TSLA, MSFT, AMZN, GOOGL, META, NVDA) didn't**: the
mega-cap 7 already receive heavy, constant coverage from the Nasdaq
category feeds by construction (confirmed live — AMD/NVDA appeared in
the very first Nasdaq Markets feed sample fetched); Dell, Salesforce,
Workday, Reddit, and Sandisk are comparatively under-covered by general
financial media, so a direct IR feed is where the marginal evidence gain
is largest. Per this milestone's own "do not require a separate feed for
every company if operationally expensive" instruction, no attempt was
made to source IR feeds for the other 7.

**Considered and explicitly rejected**: scraping any site without an RSS
feed, unofficial/aggregator mirrors of the above sources, and any paid
news API — none were necessary once the official Nasdaq category feeds
and official company IR feeds were located.

**Feed configuration shape** (`RSSFeedSource`,
`app/config/models.py` — the canonical definition;
`app/providers/rss/models.py` re-exports it so both the actual runtime
wiring (`AppSettings.rss_feed_urls` in `app.bootstrap`) and the
configuration-validation/inspection endpoints share one shape and can
never drift apart): each `RSS_FEED_URLS` array element is either a bare
URL string (the pre-Priority-6 shape, still fully supported — a
`model_validator(mode="before")` treats a plain string as `{"url":
string}`) or an object `{"url", "name", "category", "tag"}`. Still one
JSON array under one env var.

**Provenance now actually reaches the persisted record.** A real gap was
found and fixed during this milestone: `KnowledgeIngestionService
._to_vector_document` computed `item.source_metadata` (feed url/title,
author) but never copied it into the `VectorDocument.metadata` dict that
`ChromaKnowledgeRepository.save_batch` actually persists — only
`RelationalRecord` carried it, and `RelationalRecord` is never written
anywhere (§12's own "not wired into `app/bootstrap.py`" limitation).
Every real ingested record's metadata now includes `feed_url`,
`feed_title`, `author`, and — new this milestone — `source_name`,
`category`, `tag` whenever the configured `RSSFeedSource` declared them.

**Cross-feed duplicate detection.** The same article reachable via two
different configured feeds (e.g. a Nasdaq category feed and a company IR
feed both syndicating the same press release) commonly carries two
different `<guid>` values — the pre-existing exact-id check
(`RejectionReason.DUPLICATE_ID`) does not catch this. A new
`RejectionReason.DUPLICATE_URL` check
(`KnowledgeIngestionService._normalized_url`) compares each item's
canonical URL (scheme+host+path, query string and trailing slash
stripped) against every already-accepted item's within the same batch —
`?utm_source=nasdaq` tracking parameters or a trailing `/` no longer
produce a second copy of the same story.

**Source health.** `RSSFeedData` (`app/providers/rss/models.py`) gained
`source_name`/`category`/`tag` (echoed from the configured
`RSSFeedSource`, not derived from fetched content) and
`fetch_duration_seconds` (this feed's own fetch+parse latency).
`summarize_feed_health()` (`app/providers/rss/provider.py`) reduces one
run's `RSSFeedData` list into a per-feed `success`/`item_count`/
`fetch_duration_seconds`/`error` snapshot. Cross-run history (last
success/failure over time, a rolling failure rate) is deliberately *not*
a new persisted store — it is read from the existing
`rss_feed_fetched`/`rss_feed_fetch_failed` structured log lines (§9),
already emitted per feed per run, e.g.:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backend \
  | grep -E "rss_feed_fetched|rss_feed_fetch_failed"
```

One dead feed's `fetch_error` was already isolated to its own
`RSSFeedData` entry before this milestone (`RSSProvider.fetch()`'s own
per-feed `_fetch_one` isolation, unchanged) — every other configured
feed's items are still collected and persisted in the same run.

**Licensing/usage considerations.** All 10 sources are publicly
accessible RSS feeds explicitly published for syndication by their own
operators (Nasdaq's own "RSS Feeds" page; each company's own official
investor-relations site) — no authentication, scraping, or terms-of-use
circumvention involved. Article text is stored and used the same way
MarketWatch's pre-existing feed already was (§11's existing "untrusted
content, never rendered as HTML" handling, unchanged).
