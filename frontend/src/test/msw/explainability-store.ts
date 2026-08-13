import { getBacktestResult } from "@/test/msw/backtesting-store";
import type {
  ContributionBreakdown,
  ExplainabilityResult,
  GenerateExplanationRequest,
  PerformanceAttribution,
  RiskExplanation,
  StrategyExplanation,
} from "@/types/explainability";

/** A tiny in-memory stand-in for the Explainability & Performance
 * Attribution Engine's durable repository (`BaseExplainabilityRepository`,
 * `app/explainability/engine.py`) — same durable-persistence semantics as
 * `backtesting-store.ts`, not the ephemeral `InMemoryResultStore` pattern
 * `result-store.ts` mirrors. */

const resultsByRequestId = new Map<string, ExplainabilityResult>();
let nextId = 1;

export function resetExplainabilityStore(): void {
  resultsByRequestId.clear();
  nextId = 1;
}

function buildContribution(source: string, category: ContributionBreakdown["category"], weight: number, contribution: number): ContributionBreakdown {
  return { source, category, weight, contribution_percent: contribution, description: `${source} contributed ${String(contribution)}%.` };
}

function buildStrategyExplanation(): StrategyExplanation {
  return {
    strategy_name: "Momentum Growth",
    alignment_score: 78,
    matched_rules: [{ rule_id: "rule-1", field: "overall_score", operator: "GREATER_THAN", weight: 1, pass_rate: 0.8, evaluated_candidate_count: 5, reason: "4 of 5 candidates satisfied this rule." }],
    failed_rules: [],
    weight_breakdown: [buildContribution("overall_score", "STRATEGY", 1, 60), buildContribution("confidence", "STRATEGY", 0.5, 20)],
    summary: "Momentum Growth aligns well with this recommendation result.",
  };
}

function buildRiskExplanation(): RiskExplanation {
  return {
    overall_risk_score: 42,
    category_breakdown: [
      { metric_name: "Sector concentration", category: "SECTOR", value: 0.6, score: 55, severity: "MODERATE", description: "Technology makes up 60% of holdings." },
      { metric_name: "Volatility Proxy", category: "VOLATILITY", value: 0.3, score: 35, severity: "MODERATE", description: "Moderate score dispersion across holdings." },
    ],
    severity_breakdown: { LOW: 1, MODERATE: 4 },
    exposure_breakdown: [
      { sector: "Technology", country: null, industry: null, weight: 0.6, holding_count: 3 },
      { sector: null, country: "US", industry: null, weight: 0.8, holding_count: 4 },
    ],
    summary: "Moderate concentration risk in Technology.",
  };
}

function buildPerformanceAttribution(backtestRunId: string): PerformanceAttribution {
  const backtestResult = getBacktestResult(backtestRunId);
  return {
    period: "2026-01-01 to 2026-02-01",
    portfolio_return: backtestResult?.portfolio_return ?? 4,
    benchmark_return: backtestResult?.benchmark_return ?? 3,
    excess_return: backtestResult?.excess_return ?? 1,
    contribution_breakdown: [
      buildContribution("Technology", "SECTOR", 0.6, 3.1),
      buildContribution("Healthcare", "SECTOR", 0.4, 0.9),
      buildContribution("US", "COUNTRY", 0.8, 3.5),
      buildContribution("DE", "COUNTRY", 0.2, 0.5),
      buildContribution("Consumer Electronics", "INDUSTRY", 0.5, 2.2),
    ],
    summary: "Sector and country exposure both contributed positively to excess return.",
  };
}

export function generateExplanation(body: GenerateExplanationRequest): ExplainabilityResult {
  const requestId = `test-explainability-${String(nextId)}`;
  nextId += 1;

  const result: ExplainabilityResult = {
    request_id: requestId,
    generated_at: "2026-02-01T00:05:00Z",
    recommendation_explanations: [
      {
        ticker: "AAPL",
        company_name: "Apple Inc.",
        overall_score: 82,
        confidence: 78,
        contributing_components: [buildContribution("screening_score", "SCREENING", 1, 30), buildContribution("research_score", "RESEARCH", 1, 25)],
        top_positive_factors: [buildContribution("screening_score", "SCREENING", 1, 30)],
        top_negative_factors: [buildContribution("alert_score", "ALERTS", 0.5, -5)],
        reasoning: "Strong evidence across screening and research.",
        summary: "AAPL scored well due to consistent screening and research signals.",
      },
    ],
    strategy_explanations: body.strategy_evaluation_id ? [buildStrategyExplanation()] : [],
    risk_explanation: body.risk_assessment_id ? buildRiskExplanation() : null,
    performance_attribution: body.backtest_run_id ? buildPerformanceAttribution(body.backtest_run_id) : null,
    overall_summary: `Explanation "${body.name}" generated from recommendation result ${body.recommendation_result_id}.`,
  };

  resultsByRequestId.set(requestId, result);
  return result;
}

/** Lets a test seed an exact `ExplainabilityResult` directly (bypassing
 * `POST /explainability`) — used by result-panel/comparison tests that
 * want known, hand-picked values. */
export function seedExplainabilityResult(result: ExplainabilityResult): void {
  resultsByRequestId.set(result.request_id, result);
}

export function getExplainabilityResult(requestId: string): ExplainabilityResult | undefined {
  return resultsByRequestId.get(requestId);
}
