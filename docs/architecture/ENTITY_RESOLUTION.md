# Entity Resolution & Company Intelligence

**Milestone 12 — post-v1.0.0 / v1.1 candidate.** This is a new capability
extending Milestone 11's ingestion pipeline; v1.0.0's own scope, status,
and sign-off are unchanged by this document. See
`docs/release/UPGRADE_POLICY.md`'s versioning rules for what a v1.1
candidate capability means in this repository.

**Milestone 13 update**: `EntityResolutionService` gained two small,
additive accessors consumed by the new Live Market Data layer —
`get_by_entity_id(entity_id)` (maps a canonical entity to its
`CompanyReference`, used to resolve `.ticker`/`.exchange`/`.currency` for
a market-data lookup) and `list_references()` (enumerates every known
canonical entity, used by the market-data refresh workflow). Neither
changes the canonical identity model itself or anything documented below
— see `docs/architecture/MARKET_DATA_ARCHITECTURE.md` for the full
Milestone 13 design.

**Milestone 14 update**: no change to `EntityResolutionService` itself.
`app.services.portfolio_market_snapshot.PortfolioMarketSnapshotService`
(new) reuses `lookup_by_name_or_ticker()` — the same method Research
already calls — to resolve each `WatchlistItem` before fetching its
market snapshot; an item that doesn't resolve is reported as
`ENTITY_NOT_MAPPED`, never guessed, exactly matching every other
consumer's treatment of an unresolved entity. See
`docs/architecture/PORTFOLIO_INTELLIGENCE.md` for the full Milestone 14
design.

## 1. Problem this milestone fixes

Milestone 11 shipped a real, working ingestion pipeline, but every
ingested record was recorded honestly as `entity_resolved: false` — no
mechanism existed to determine *which company* a given article was about.
Research could retrieve semantically relevant articles and return
evidence/news, but could not reliably associate them with a canonical
company identity, and routinely surfaced `ENTITY_NOT_RECOGNIZED` for real
companies (e.g. Dell) simply because they weren't in the one small,
hardcoded keyword set the rest of the system already depended on.

## 2. Canonical company identity — the gap, and what this milestone does about it

Before writing any resolution logic, this milestone inspected the
existing codebase for a usable canonical company representation (per its
own §2 instruction). Two candidates existed, and neither was directly
usable as-is:

- **`app.market_data.models.CompanyProfile`** — the richer shape (ticker,
  company_name, exchange, country, sector, industry) — but in this
  deployment it is only ever populated by
  `app.providers.market_data.mock.MockMarketDataProvider`, which
  synthesizes a **fake** company name (`f"{ticker} Mock Corp"`) for any
  ticker. Using it as an entity-resolution reference source would mean
  matching real article text against fabricated company names — a direct
  violation of this codebase's "no fabricated data" rule (carried over
  from Milestone 11's own explicit constraint). **Documented gap, not
  used.**
- **`app.services.market_intelligence.engine.COMPANY_KEYWORDS`** — a
  small, hand-maintained `dict[str, tuple[str, ...]]` (canonical name ->
  real aliases/ticker) already used by `MarketIntelligenceEngine`,
  `EvidenceEngine`, and `CompanyResearchAgent.resolve_company_name()`.
  Real facts, but only 7 companies, and no ticker/exchange/sector/
  industry/country fields — a `dict[str, tuple[str,...]]` has no room for
  them.

Per this milestone's own explicit constraint ("do not invent a second
company entity model"), the fix was to **extend, not replace**:

1. `COMPANY_KEYWORDS` itself gained five new real, publicly-known entries
   (Dell Technologies, Salesforce, Workday, Reddit, SanDisk) — the exact
   companies Milestone 11's own live Docker acceptance run ingested from
   a real MarketWatch feed. This directly fixes `entity_recognized`/
   `ENTITY_NOT_RECOGNIZED` for those companies through the pre-existing
   mechanism, with zero change to `MarketIntelligenceEngine`'s or
   `EvidenceEngine`'s own logic.
2. `app.services.entity_resolution.reference_data.get_company_reference_data()`
   builds a richer `CompanyReference` record (entity_id, canonical_name,
   legal_name, ticker, exchange, country, sector, industry, aliases) **on
   top of** `COMPANY_KEYWORDS` — one company name/alias set, two views of
   the same data. A consistency check (exercised by this module's own
   tests) fails loudly if a `COMPANY_KEYWORDS` entry is ever added without
   a corresponding richer record.

```
COMPANY_KEYWORDS (name -> aliases)          <- MarketIntelligenceEngine, EvidenceEngine
        |
        v  (+ ticker/exchange/country/sector/industry/legal_name)
CompanyReference (richer, structured)       <- EntityResolutionService
```

## 3. Entity extraction & candidate generation

`app.services.entity_resolution.service.EntityResolutionService` —
deterministic, provider-agnostic, no LLM call. Candidate generation scans
a piece of text (typically an article's title + summary) for
whole-word/phrase, case-insensitive matches against each `CompanyReference`'s:

- canonical name (`ResolutionMethod.EXACT_NAME`)
- legal name (`ResolutionMethod.LEGAL_NAME`)
- aliases (`ResolutionMethod.ALIAS`)
- ticker, matched **case-sensitively** (`ResolutionMethod.TICKER`)

Word-boundary regex matching (the same technique `MarketIntelligenceEngine`
already uses) means a short term like "IT" never substring-matches inside
an unrelated word, and Unicode-aware boundaries mean a possessive form
("Dell's", "Dell’s") still matches correctly.

**Ticker case-sensitivity is deliberate.** Several real tickers double as
ordinary English words/abbreviations (e.g. `CRM` — "customer relationship
management"). Matching a ticker only in its real uppercase financial-text
form (`"(NYSE: CRM)"`, `"CRM shares rose"`) — not generic lowercase
(`"crm software"`) — was verified necessary during implementation: a naive
case-insensitive alias match on `"CRM"` (present in `COMPANY_KEYWORDS` as
both an alias and the ticker) produced exactly this false positive before
the fix. Aliases that literally duplicate a reference's ticker in its
exact upper-case form are excluded from the generic (case-insensitive)
alias path for this reason — the ticker is still matched, only via the
stricter path.

Safe on any input: `re.escape()` on every matched term means adversarial
or malformed text (HTML tags, SQL-like strings, arbitrary Unicode,
regex metacharacters) is scanned as inert data and never raises or
changes behavior (see §12, Security).

## 4. Scoring

Every match contributes a transparent, explainable base score by method
(strongest to weakest signal):

| Method | Base score | Why |
|---|---|---|
| Exact canonical name | 0.90 | Least ambiguous signal |
| Legal name | 0.85 | Formal, but usually appears less often in news prose |
| Alias | 0.75 | A short/common form, more likely to also mean something else |
| Ticker (case-sensitive) | 0.65 | Shortest, most likely to collide with an ordinary word/abbreviation |

Adjustments, applied per candidate:

- **Title bonus** (+0.15): the matched term appears in the title, not
  only the body — title-vs-body weighting (§5's own requirement).
- **Occurrence bonus** (+0.03 per occurrence beyond the first, capped at
  +0.12): repeated mentions of the same entity add modest confidence,
  with diminishing returns rather than unbounded inflation from a
  long/repetitive article.
- **Ambiguity penalty** (×0.85, applied to *every* candidate): when more
  than one distinct company is found in the same text, every candidate's
  score is reduced — conflicting candidates should never each look as
  confident as they would in isolation.

Every `EntityCandidate` on `EntityResolutionResult.candidates` carries its
`method`, `score`, `matched_terms`, `occurrence_count`, and `title_match`
— nothing is a black-box number; a caller can always see exactly why a
score is what it is.

## 5. Confidence thresholds & policy

| Tier | Meaning | Behavior |
|---|---|---|
| `HIGH` | Safe for automatic resolution | Entity attached (`entity_id` set) |
| `MEDIUM` | Genuine evidence, but not certain | Entity attached, `entity_needs_review: true` |
| `LOW` | A candidate exists, but confidence is too low | **Not** attached — article retained, unassociated |
| `UNRESOLVED` | No candidate matched at all | Not attached |

Configurable defaults (`ENTITY_MATCH_HIGH_THRESHOLD=0.85`,
`ENTITY_MATCH_MEDIUM_THRESHOLD=0.5`, both in `.env.example`): a candidate
must score at or above `high_threshold` **and** not be ambiguous (see
below) to be `HIGH`; at or above `medium_threshold` otherwise attaches as
`MEDIUM`; below that, `LOW`; no candidates at all, `UNRESOLVED`.

**Ambiguity handling**: if the top two candidates' scores are within a
0.15 margin of each other, the result is downgraded to at most `MEDIUM`
— a second real explanation too close to rule out is never silently
resolved as `HIGH`. Combined with the ambiguity penalty (§4), this is how
"an ambiguous company remains unresolved/medium-confidence rather than
being guessed" (this milestone's own §6/§18 requirement) is actually
enforced, not just documented.

## 6. Multi-entity support

An article's `EntityResolutionResult` has one `primary` (the
highest-scoring candidate, when the tier is `HIGH`/`MEDIUM`) and zero or
more `secondary` candidates (every other candidate that still scores at
or above `medium_threshold`, capped at `ENTITY_MAX_CANDIDATES`). The
knowledge record is never duplicated per company — `secondary_entity_ids`
is stored as one comma-joined string field on the same record.

## 7. Knowledge Hub enrichment

`KnowledgeIngestionService` gained an optional `entity_resolver`
constructor parameter (default `None` — when omitted, behavior is
byte-for-byte identical to pre-Milestone-12: `entity_resolved: false` on
every record, no other entity fields). When provided, each item's
title/summary is resolved and shaped into flat metadata fields via the
shared `app.services.entity_resolution.metadata.build_entity_metadata()`
— the single source of truth also used by the backfill service (§9), so
a freshly-ingested record and a backfilled one are shaped identically.

Metadata fields written (only present when a value applies — Chroma
rejects `None` values, so absent means "not applicable," never a
placeholder):

| Field | Always present? | Meaning |
|---|---|---|
| `entity_resolved` | always | `true` only for HIGH/MEDIUM |
| `entity_confidence_tier` | always | `HIGH`/`MEDIUM`/`LOW`/`UNRESOLVED` |
| `entity_id` | HIGH/MEDIUM only | The resolved entity's stable id |
| `company` | HIGH/MEDIUM only | Same value as `entity_id` — see §8 |
| `entity_canonical_name` | HIGH/MEDIUM only | |
| `entity_ticker` | HIGH/MEDIUM only, if known | |
| `entity_confidence` | HIGH/MEDIUM only | The primary candidate's score |
| `entity_resolution_method` | HIGH/MEDIUM only | |
| `entity_needs_review` | HIGH/MEDIUM only | `true` for MEDIUM |
| `secondary_entity_ids` | if any exist | comma-joined |

All existing provenance fields (`ingested_at`, `url`, `published_at`,
`source_provider_id`, `title`) are unchanged and untouched.

## 8. Chroma metadata & the `company` structured filter

This deployment's only active knowledge repository is
`ChromaKnowledgeRepository` (see `MARKET_INTELLIGENCE_INGESTION.md` — no
Postgres-backed path is wired into `app.bootstrap`), so per this
milestone's own §9/§22 preference, all entity metadata lives in existing
Chroma metadata — no new vector store, no PostgreSQL migration.

**A pre-existing gap this milestone completed, not introduced**:
`KnowledgeHub.search(KnowledgeSearchFilters(company=...))` already built a
Chroma `where={"company": ...}` structured filter — but no record had
ever set a `"company"` metadata key before Milestone 12, so this filter
path was silently dead code in production. `KnowledgeIngestionService`
now sets `metadata["company"] = entity_id` (duplicating `entity_id` under
this pre-existing key) specifically so this already-designed-for filter
becomes usable, without changing `KnowledgeHub`'s own (already-tested)
code or its test's literal `{"company": "Apple"}` assertion.

A second, deeper gap surfaced while wiring this up and was also fixed:
`ChromaKnowledgeRepository.search()` unconditionally called ChromaDB's
nearest-neighbor `query()`, which requires text to rank by — a
filters-only `SearchQuery` (no `query_text`, the exact shape entity-aware
retrieval needs) always returned `[]`, regardless of what `filters`
contained. It now uses ChromaDB's own `get(where=...)` for a pure
metadata-filter lookup with no ranking, only falling back to `[]` when
there's genuinely neither text nor filters to search by.

Existing records (ingested before Milestone 12, no entity metadata at
all) remain fully queryable through every existing path — this is purely
additive metadata on top of an unchanged storage model.

## 9. Backfill

`app.services.entity_resolution.backfill.EntityResolutionBackfillService`
— resolves entities for already-ingested records, retroactively.

- **Never rewrites article content.** Uses ChromaDB's `update()` (not
  `upsert()`): `update()` only changes the fields explicitly passed
  (here, only `metadatas`); this repository never re-fetches or
  re-supplies document text.
- **Idempotent by construction.** Resolution is a pure function of a
  record's own stored text — re-running against already-backfilled
  records recomputes and rewrites the identical outcome, not a different
  one. A record that previously resolved but no longer does (e.g. an
  edited reference set) has its stale `entity_id`/`company`/etc. fields
  explicitly stripped before the fresh (empty) result is merged in — it
  never keeps pointing at an entity it no longer resolves to.
- **Paginated / resumable.** `list_all(limit, offset)` processes the
  collection page by page (`batch_size`, default 100) rather than loading
  everything into memory; an interrupted run can simply be rerun (safe,
  by the idempotency guarantee above).
- **Dry-run.** `run(dry_run=True)` resolves and counts every record
  without writing anything — preview a backfill's outcome first.
- **Partial-failure safe.** A page that fails to write is recorded in
  `BackfillResult.errors`; every other page still completes.

### Operational trigger

Mirrors Milestone 11's `scripts/run_ingestion.py` convention exactly —
container-exec only, never an HTTP endpoint:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec backend python scripts/run_entity_backfill.py [--dry-run] [--batch-size N]
```

Prints a JSON `BackfillResult` summary to stdout; exits `0` on success
(including a completed dry run), `1` if entity resolution or the
knowledge repository isn't configured, or if the run itself reported
errors. Never prints a token, password, or `.env` value.

## 10. Research integration

`CompanyResearchAgent` gained an optional `entity_resolver` constructor
parameter (default `None` — identical pre-Milestone-12 behavior when
omitted). When provided:

1. `request.company_name`/`.ticker` is resolved to a canonical entity via
   `EntityResolutionService.lookup_by_name_or_ticker()` — a direct
   identifier lookup (the caller already told us the name/ticker; no
   ambiguity/scoring applies, unlike free-text `resolve()`).
2. `_fetch_company_records` fetches entity-tagged records (via
   `KnowledgeHub.search(KnowledgeSearchFilters(company=entity_id))`) and
   places them first, then appends the pre-existing semantic search
   (`KnowledgeHub.query(company_name)`) results, deduplicated by id.

**Semantic search always still runs — it is supplemented, never
replaced.** If nothing resolves (unknown company, no resolver configured)
or no entity-tagged records exist yet (e.g. only pre-Milestone-12 data),
retrieval is identical to the pre-Milestone-12 semantic-only path.

`CompanyOverview` gained purely additive optional fields — populated only
when an entity actually resolved: `resolved_entity_id`,
`resolution_confidence` (always `1.0` for a direct lookup — it's a
confirmed identifier match, not a scored text guess),
`resolution_method` (`"direct_lookup"`), `sector`, `industry`, `country`.
The pre-existing `entity_recognized`/`mention_count` fields
(`MarketIntelligenceEngine`'s own per-request keyword detection over
*retrieved* records) are untouched — a separate, narrower signal, not
replaced by the new fields. Because `COMPANY_KEYWORDS` itself grew (§2),
`entity_recognized` and the `ENTITY_NOT_RECOGNIZED` risk flag also
improve for the five newly-added companies, through that pre-existing
mechanism, with no code changes to it.

`sector_analysis`/`country_exposure` (report sections 5-6, driven by
`RelationshipEngine`/`MarketIntelligenceEngine`'s own keyword-based
sector/country *text* detection) remain an independent signal from the
new `CompanyOverview.sector`/`.country` fields (a direct reference-data
lookup) — both are honest, just computed from different evidence; a
report can show a populated `company_overview.sector` while still
carrying a `NO_SECTOR_CONTEXT` risk flag if the article text itself
doesn't separately mention sector-indicating keywords. This is a known,
accepted characteristic, not a bug — reconciling the two was out of this
milestone's scope (it would mean changing `RelationshipEngine`'s own
logic, not extending the entity-resolution layer).

## 11. Configuration

All in `AppSettings` (`app/bootstrap.py`), documented in `.env.example`:

| Setting | Default | Meaning |
|---|---|---|
| `ENTITY_RESOLUTION_ENABLED` | `true` | Unlike `INGESTION_ENABLED`, defaults on — resolution starts no new scheduled job and calls no external service, so there's no "upgrading silently changes runtime behavior" risk to guard against. |
| `ENTITY_MATCH_HIGH_THRESHOLD` | `0.85` | |
| `ENTITY_MATCH_MEDIUM_THRESHOLD` | `0.5` | |
| `ENTITY_MAX_CANDIDATES` | `5` | |

An invalid threshold combination (`medium > high`) or `max_candidates < 1`
degrades `entity_resolution_service` to `None` (logged) — the same
"never crash startup over bad optional config" shape every other
dependency in `app.bootstrap` already uses. No secret is required —
deterministic, local, in-process matching only.

## 12. Observability

Reuses existing structured-logging conventions (stdlib `logging`,
`extra={}`) — no new telemetry framework:

- `MorningPipeline`'s own pre-existing `ingestion_run_completed` log line
  already computed `entity_resolved_count`/`entity_unresolved_count` from
  each batch's `VectorDocument.metadata["entity_resolved"]` (Milestone 11
  wired the field, always `False`, into that count). No pipeline code
  changed for this milestone — the count is now simply real, since
  `entity_resolved` is now a genuine computed value.
- `entity_backfill_completed` (`app.services.entity_resolution.backfill`)
  — one line per run: `dry_run`, `records_processed`, `records_updated`,
  per-tier counts, `error_count`, `duration_seconds`.

## 13. Security

- **Untrusted text, never executed.** Article title/summary text (RSS
  content, per Milestone 11's own security model) is scanned only by
  read-only regex matching — never rendered as HTML, evaluated, or
  passed to any executable context. Verified by test
  (`test_resolve_treats_html_and_script_content_as_plain_text_never_executed`).
- **No new fetch surface.** This module makes no HTTP call, opens no
  connection, and accepts no URL — no SSRF path exists here at all.
- **No external model provider.** Purely local, deterministic string
  matching — no LLM, no third-party API, no data ever leaves the process.
- **No prompt-injection path.** Nothing in this module constructs a
  prompt or invokes an LLM; resolution output (`EntityResolutionResult`)
  is structured data consumed by other structured code, never
  interpolated into a system/user prompt.
- **Safe on malformed input.** `re.escape()` on every matched term and
  exception-free handling of empty/adversarial text (§3) means untrusted
  content can't crash resolution or corrupt matching.

## 14. Known limitations

- **Static reference set.** Only the companies in `COMPANY_KEYWORDS` (12
  as of this milestone) can ever resolve — no external company database,
  no fuzzy/ML-based matching. A real company not yet in the set correctly
  stays `UNRESOLVED`, not guessed.
- **No cross-lingual matching.** Company names/aliases are matched as
  literal English-language strings; a company referred to only in another
  language's spelling won't match.
- **`sector_analysis`/`country_exposure` (Research report sections 5-6)
  are not reconciled with the new resolved-entity `sector`/`country`
  fields** — see §10's own note; both are honest, independently-computed
  signals, left unreconciled as an explicit scope boundary.
- **Direct lookup confidence is always 1.0.** `lookup_by_name_or_ticker`
  (used for a Research *request*'s own company_name/ticker) has no
  ambiguity to score — a caller-supplied identifier either matches the
  reference set exactly/by substring, or it doesn't. This is a different,
  simpler operation than `resolve()`'s free-text candidate scoring (§3-5),
  and is documented as such rather than forcing an artificial score.
- **Single-process, no distributed backfill coordination.** Running the
  backfill script from multiple places concurrently is safe (idempotent)
  but redundant — no distributed lock, matching the same characteristic
  already documented for the Milestone 11 scheduler.
