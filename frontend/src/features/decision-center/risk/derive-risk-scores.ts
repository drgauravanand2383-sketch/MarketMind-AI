import type { RiskCategory, RiskMetric } from "@/types/portfolio";

/** `RiskAssessment` has no flat `diversification_score`/`concentration_score`/
 * `liquidity_score`/`volatility_score` field — those concepts only exist as
 * entries inside `risk_metrics`, each keyed by `category`
 * (`app/risk/models.py`). This derives the four named scores the spec asks
 * for by filtering on that category, never inventing a value the backend
 * didn't compute. Returns `null` for a category the engine didn't emit a
 * metric for (a real possibility — e.g. `MARKET_CAP` is documented to
 * always score 0 with an "insufficient data" description, not fabricated). */
export function findRiskMetricByCategory(metrics: RiskMetric[], category: RiskCategory): RiskMetric | null {
  return metrics.find((metric) => metric.category === category) ?? null;
}

export interface DerivedRiskScores {
  diversification: RiskMetric | null;
  concentration: RiskMetric | null;
  liquidity: RiskMetric | null;
  volatility: RiskMetric | null;
}

export function deriveRiskScores(metrics: RiskMetric[]): DerivedRiskScores {
  return {
    diversification: findRiskMetricByCategory(metrics, "DIVERSIFICATION"),
    concentration: findRiskMetricByCategory(metrics, "CONCENTRATION"),
    liquidity: findRiskMetricByCategory(metrics, "LIQUIDITY"),
    volatility: findRiskMetricByCategory(metrics, "VOLATILITY"),
  };
}
