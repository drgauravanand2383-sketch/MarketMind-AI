/**
 * Mirrors `app.risk.models`, `app.recommendations.models`, and
 * `app.agents.portfolio_intelligence.models` field-for-field (verified
 * against the actual backend source, Frontend Milestones 3 and 5). There
 * is no separate `Portfolio` domain model — `portfolio_id` *is* a
 * `watchlist_id`; `GET /portfolio` and `GET /portfolio/{id}` return the
 * exact `Watchlist` shape (`@/types/watchlist`). Summary/intelligence/
 * risk/recommendations are all computed on demand from a watchlist's
 * `items` — nothing here is computed on the frontend (M3 spec).
 *
 * `RiskCategory`/`RiskSeverity`/`RecommendationType` *are* closed Python
 * `str` enums (unlike `sector`/`country`/`theme` elsewhere) — modeled as
 * string-literal unions, the same convention `UserStatus` established.
 *
 * Milestone 5 note — `RiskAssessment` has no flat `diversification_score`/
 * `concentration_score`/`liquidity_score`/`volatility_score` field. Those
 * concepts exist only as entries inside `risk_metrics`, keyed by
 * `category` (`DIVERSIFICATION`/`CONCENTRATION`/`LIQUIDITY`/`VOLATILITY`)
 * — derive them by filtering `risk_metrics` client-side
 * (`@/features/decision-center/risk/derive-risk-scores.ts`), never invent
 * a field the backend doesn't have.
 *
 * Milestone 14 note — live market data. `RecommendationCandidate`,
 * `RiskAssessment`, and `PortfolioIntelligenceReport` all gained purely
 * additive market-data fields (`app.services.market_snapshot.models`/
 * `app.services.portfolio_market_snapshot.models`, backend). Every new
 * field is optional here — a report/candidate/assessment built before
 * this milestone (or via `agent.run()` directly, bypassing the REST
 * handler that attaches it) simply omits them. `MarketSnapshotStatus`
 * mirrors `app.services.market_snapshot.models.MarketSnapshotStatus`
 * exactly; never re-interpreted or coarsened client-side.
 */

import type { Alert } from "@/types/alerts";
import type { CompanyResearchReport } from "@/types/research";
import type { ScreenResult } from "@/types/screening";
import type { SignalResult } from "@/types/signals";

export type RiskCategory =
  | "DIVERSIFICATION"
  | "CONCENTRATION"
  | "SECTOR"
  | "GEOGRAPHIC"
  | "VOLATILITY"
  | "LIQUIDITY"
  | "STYLE"
  | "MARKET_CAP"
  | "CUSTOM";

export type RiskSeverity = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export interface RiskMetric {
  metric_name: string;
  category: RiskCategory;
  value: number;
  score: number;
  severity: RiskSeverity;
  description: string;
}

/** Exactly one of `sector`/`country`/`industry` is populated per entry. */
export interface PortfolioExposure {
  sector: string | null;
  country: string | null;
  industry: string | null;
  weight: number;
  holding_count: number;
}

/** Mirrors `app.services.market_snapshot.models.MarketSnapshotStatus`. */
export type MarketSnapshotStatus =
  | "FRESH"
  | "STALE"
  | "ENTITY_NOT_MAPPED"
  | "PROVIDER_UNAVAILABLE"
  | "PROVIDER_TIMEOUT"
  | "RATE_LIMITED"
  | "INVALID_RESPONSE"
  | "NO_DATA"
  | "UNAVAILABLE";

/** Mirrors `app.services.market_snapshot.models.MarketSnapshot`. */
export interface MarketSnapshot {
  entity_id: string;
  canonical_name: string;
  ticker: string;
  exchange: string | null;
  currency: string | null;
  price: number;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  day_high: number | null;
  day_low: number | null;
  volume: number | null;
  quoted_at: string;
  fetched_at: string;
  provider: string;
  trading_status: string | null;
}

/** Mirrors `app.services.market_snapshot.models.MarketSnapshotResult`.
 * `snapshot` is populated only when `status` is `FRESH`/`STALE`. */
export interface MarketSnapshotResult {
  entity_id: string;
  status: MarketSnapshotStatus;
  snapshot: MarketSnapshot | null;
  reason: string;
}

/** Mirrors `app.workflows.market_data_refresh.models.MarketDataRefreshResult`
 * — the `MARKET_SNAPSHOT_REFRESHED` WS event payload (Milestone 14). */
export interface MarketDataRefreshResult {
  execution_id: string;
  started_at: string;
  completed_at: string;
  entities_requested: number;
  fresh_count: number;
  stale_count: number;
  unavailable_count: number;
  results: MarketSnapshotResult[];
}

/** Mirrors `app.risk.models.MarketDataCoverageStatus`. */
export type MarketDataCoverageStatus = "NOT_EVALUATED" | "NONE" | "PARTIAL" | "FULL";

/** Mirrors `app.risk.models.MarketDataCoverage` — purely informational;
 * never affects `overall_risk_score`/`risk_metrics`. */
export interface MarketDataCoverage {
  status: MarketDataCoverageStatus;
  fresh_count: number;
  stale_count: number;
  unavailable_count: number;
  not_evaluated_count: number;
  total_candidates: number;
}

export interface RiskAssessment {
  request_id: string;
  overall_risk_score: number;
  overall_severity: RiskSeverity;
  risk_metrics: RiskMetric[];
  exposures: PortfolioExposure[];
  recommendations: string[];
  summary: string;
  /** Milestone 14, additive. Absent on an assessment computed before this
   * milestone (or read from a not-yet-migrated stored row). */
  market_data_coverage?: MarketDataCoverage;
  generated_at: string;
}

export type RecommendationType = "STRONG_BUY" | "BUY" | "WATCH" | "HOLD" | "AVOID";

/** Mirrors `app.recommendations.models.MarketContribution` — whether live
 * market data informed this candidate's score. Always present (defaults
 * to `"none"` backend-side), never a hidden/opaque signal: `"direct"` a
 * fresh/stale snapshot was supplied for this ticker; `"indirect"` no
 * direct snapshot, but a triggered supporting signal referenced live
 * market data; `"none"` neither applies. */
export type MarketContribution = "direct" | "indirect" | "none";

export interface RecommendationCandidate {
  ticker: string;
  company_name: string | null;
  country: string | null;
  sector: string | null;
  industry: string | null;
  overall_score: number;
  confidence: number;
  recommendation: RecommendationType;
  reasoning: string;
  supporting_signals: SignalResult[];
  supporting_alerts: Alert[];
  screening_score: number | null;
  planning_score: number | null;
  research_score: number | null;
  portfolio_score: number | null;
  signal_score: number | null;
  alert_score: number | null;
  /** Milestone 14, additive — all `null`/`"none"` on a candidate scored
   * before this milestone. Never fabricated: `null` unless a real
   * FRESH/STALE snapshot was supplied for this ticker. */
  market_price?: number | null;
  market_change_percent?: number | null;
  market_freshness?: MarketSnapshotStatus | null;
  market_snapshot?: MarketSnapshotResult | null;
  market_contribution?: MarketContribution;
  created_at: string;
}

export interface RecommendationSummary {
  strong_buy: number;
  buy: number;
  watch: number;
  hold: number;
  avoid: number;
  average_score: number;
  average_confidence: number;
}

export interface RecommendationResult {
  request_id: string;
  generated_at: string;
  total_candidates: number;
  recommendations: RecommendationCandidate[];
  summary: RecommendationSummary;
}

export interface PortfolioOverview {
  portfolio_name: string;
  holding_count: number;
  matched_holding_count: number;
  generated_at: string;
}

export interface CompanySummary {
  company_name: string;
  ticker: string | null;
  weight: number | null;
  resolved_company_name: string;
  matched: boolean;
  entity_recognized: boolean;
  overall_confidence: number;
  narrative_summary: string | null;
}

export interface SectorOverlap {
  sector: string;
  company_names: string[];
  total_weight: number;
  is_shared: boolean;
}

export interface DataQualityFlag {
  code: string;
  description: string;
  affected_company_count: number;
  affected_companies: string[];
}

export interface PortfolioEvidenceReference {
  record_id: string;
  source: string | null;
  provider: string | null;
  url: string | null;
  published_at: string | null;
  title: string | null;
  company_names: string[];
  is_shared: boolean;
}

/** One candidate's bundle of already-computed subsystem outputs — the
 * recommendation engine never fetches Screening/Signals/Alerts/Research
 * itself (module docstring, `app/recommendations/models.py`), so the
 * caller supplies whatever it already has. Milestone 5's "Generate
 * recommendations" UI only populates the identity fields
 * (`ticker`/`company_name`/`sector`/`country`/`industry`) — by explicit
 * product decision, evidence attachment (screening/research/signals/
 * alerts) is out of this milestone's UI scope, though the type is
 * modeled in full since the request schema accepts it. */
export interface CandidateEvidence {
  ticker: string;
  company_name?: string | null;
  country?: string | null;
  sector?: string | null;
  industry?: string | null;
  screening_result?: ScreenResult | null;
  signals?: SignalResult[];
  alerts?: Alert[];
  research_report?: CompanyResearchReport | null;
  portfolio_summary?: CompanySummary | null;
  planning_score?: number | null;
}

/** Body for `POST /portfolio/recommendations` (perm `portfolio:recommend`
 * — distinct from the `portfolio:read` the GET uses). */
export interface GenerateRecommendationsRequest {
  portfolio_id: string;
  evidence?: CandidateEvidence[];
  max_recommendations?: number;
  minimum_score?: number;
}

/** Mirrors `app.services.portfolio_market_snapshot.models.ValuationStatus`
 * — a single member today: `WatchlistItem` carries no quantity/position
 * size/market value anywhere, so an aggregate portfolio value is never
 * computed, never fabricated. */
export type ValuationStatus = "VALUATION_UNAVAILABLE";

/** Mirrors `app.services.portfolio_market_snapshot.models
 * .PortfolioMarketSnapshot`. */
export interface PortfolioMarketSnapshot {
  portfolio_id: string;
  generated_at: string;
  company_snapshots: MarketSnapshotResult[];
  valuation_status: ValuationStatus;
  valuation_unavailable_reason: string;
  fresh_count: number;
  stale_count: number;
  unavailable_count: number;
  entity_not_mapped_count: number;
}

export interface PortfolioIntelligenceReport {
  /** The original request that generated this report — not rendered by
   * this milestone, so left unmodeled rather than guessed. */
  request: unknown;
  generated_at: string;
  executive_summary: string;
  portfolio_overview: PortfolioOverview;
  company_summaries: CompanySummary[];
  sector_exposure: SectorOverlap[];
  concentration_observations: string[];
  relationship_observations: string[];
  notable_market_events: string[];
  evidence_summary: PortfolioEvidenceReference[];
  data_quality_notes: DataQualityFlag[];
  /** Milestone 14, additive — attached by `GET /portfolio/intelligence`
   * via `PortfolioMarketSnapshotService`, never computed by the agent
   * itself. Absent when a report was built without that extra step
   * (e.g. directly from `PortfolioIntelligenceAgent.run()`). */
  market_snapshot?: PortfolioMarketSnapshot | null;
}
