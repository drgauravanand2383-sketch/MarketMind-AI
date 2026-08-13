import type { PortfolioExposure, RiskMetric, RiskSeverity } from "@/types/portfolio";
import type { RuleAlignment } from "@/types/strategy";

/**
 * Mirrors `app.explainability.models` field-for-field (verified against
 * the actual backend source, Frontend Milestone 6). One
 * `ExplainabilityRequest`/`ExplainabilityResult` covers Recommendation,
 * Strategy, and Risk explanations plus Performance Attribution all
 * together — not four separate request "modes". `recommendation_result_id`
 * is the one required input; `strategy_evaluation_id`/`risk_assessment_id`/
 * `backtest_run_id` are optional add-ons, each unlocking exactly one
 * extra section of the result (`strategy_explanations`, `risk_explanation`,
 * `performance_attribution` respectively) only when supplied.
 *
 * "Performance Attribution" is **not** a separate backend domain — it is
 * the optional `performance_attribution` field on `ExplainabilityResult`.
 * `PerformanceAttribution.period` is a single label for the whole
 * backtest, not a time series — there is no per-period-over-time
 * attribution data anywhere in the backend (see
 * `docs/frontend/MILESTONE_6.md` for the approved "single-snapshot
 * attribution panel" design this drove).
 */

export type AttributionCategory =
  | "PLANNING"
  | "SCREENING"
  | "SIGNALS"
  | "ALERTS"
  | "RESEARCH"
  | "PORTFOLIO_INTELLIGENCE"
  | "STRATEGY"
  | "RISK"
  | "SECTOR"
  | "COUNTRY"
  | "INDUSTRY"
  | "CUSTOM";

export const ATTRIBUTION_CATEGORIES: AttributionCategory[] = [
  "PLANNING",
  "SCREENING",
  "SIGNALS",
  "ALERTS",
  "RESEARCH",
  "PORTFOLIO_INTELLIGENCE",
  "STRATEGY",
  "RISK",
  "SECTOR",
  "COUNTRY",
  "INDUSTRY",
  "CUSTOM",
];

export interface ContributionBreakdown {
  source: string;
  category: AttributionCategory;
  weight: number;
  contribution_percent: number;
  description: string;
}

export interface RecommendationExplanation {
  ticker: string;
  company_name: string | null;
  overall_score: number;
  confidence: number;
  contributing_components: ContributionBreakdown[];
  top_positive_factors: ContributionBreakdown[];
  top_negative_factors: ContributionBreakdown[];
  reasoning: string;
  summary: string;
}

export interface StrategyExplanation {
  strategy_name: string;
  alignment_score: number;
  matched_rules: RuleAlignment[];
  failed_rules: RuleAlignment[];
  weight_breakdown: ContributionBreakdown[];
  summary: string;
}

/** `category_breakdown` reuses the risk domain's own `RiskMetric`
 * (a different, more granular taxonomy than `AttributionCategory` —
 * deliberately not remapped, per the backend's own docstring), re-sorted
 * by score descending; never recalculated. */
export interface RiskExplanation {
  overall_risk_score: number;
  category_breakdown: RiskMetric[];
  severity_breakdown: Partial<Record<RiskSeverity, number>>;
  exposure_breakdown: PortfolioExposure[];
  summary: string;
}

/** `portfolio_return`/`benchmark_return`/`excess_return` are copied
 * verbatim from the resolved `BacktestResult` — same percentage scale.
 * `period` is a single label for the whole backtest, not a series. */
export interface PerformanceAttribution {
  period: string;
  portfolio_return: number;
  benchmark_return: number;
  excess_return: number;
  contribution_breakdown: ContributionBreakdown[];
  summary: string;
}

export interface ExplainabilityResult {
  request_id: string;
  generated_at: string;
  recommendation_explanations: RecommendationExplanation[];
  strategy_explanations: StrategyExplanation[];
  risk_explanation: RiskExplanation | null;
  performance_attribution: PerformanceAttribution | null;
  overall_summary: string;
}

export interface GenerateExplanationRequest {
  name: string;
  recommendation_result_id: string;
  strategy_evaluation_id?: string | null;
  risk_assessment_id?: string | null;
  backtest_run_id?: string | null;
}
