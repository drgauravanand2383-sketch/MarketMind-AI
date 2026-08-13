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

export interface RiskAssessment {
  request_id: string;
  overall_risk_score: number;
  overall_severity: RiskSeverity;
  risk_metrics: RiskMetric[];
  exposures: PortfolioExposure[];
  recommendations: string[];
  summary: string;
  generated_at: string;
}

export type RecommendationType = "STRONG_BUY" | "BUY" | "WATCH" | "HOLD" | "AVOID";

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
}
