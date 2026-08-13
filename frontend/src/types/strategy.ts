/**
 * Mirrors `app.strategy.models` field-for-field (verified against the
 * actual backend source, Frontend Milestone 5). Strategy Evaluation is
 * **population-level, not per-candidate**: a `StrategyMatch` scores how
 * well an entire `RecommendationResult` aligns with one strategy — there
 * is no per-ticker "this candidate matches this strategy" field anywhere
 * in the real model. `StrategyEvaluationRequest.recommendation_result_id`
 * must be an already-computed `RecommendationResult.request_id`
 * (`@/types/portfolio`) — the strategy engine never fetches recommendations
 * itself.
 */

export type StrategyOperator =
  | "EQUALS"
  | "NOT_EQUALS"
  | "GREATER_THAN"
  | "GREATER_EQUAL"
  | "LESS_THAN"
  | "LESS_EQUAL"
  | "BETWEEN"
  | "IN"
  | "NOT_IN";

export type StrategyType = "VALUE" | "GROWTH" | "DIVIDEND" | "QUALITY" | "MOMENTUM" | "BALANCED" | "INCOME" | "CUSTOM";

export interface StrategyWeighting {
  overall_score: number;
  screening_score: number;
  planning_score: number;
  research_score: number;
  portfolio_score: number;
  signal_score: number;
  alert_score: number;
}

/** `field` must be one of `RecommendationCandidate`'s own scalar field
 * names (never `supporting_signals`/`supporting_alerts`). */
export interface StrategyRule {
  id: string;
  field: string;
  operator: StrategyOperator;
  value: unknown;
  weight: number;
  enabled: boolean;
}

export interface InvestmentStrategy {
  id: string;
  name: string;
  description: string;
  strategy_type: StrategyType;
  enabled: boolean;
  weightings: StrategyWeighting;
  rules: StrategyRule[];
  created_at: string;
  updated_at: string;
}

export interface EvaluateStrategyRequest {
  recommendation_result_id: string;
  /** Empty means every strategy — evaluated and ranked in one call,
   * server-side; the frontend never has to call evaluate once per strategy
   * to build a comparison. */
  strategy_ids?: string[];
}

/** One `StrategyRule`'s population-level outcome — the fraction of
 * candidates (among those where the field was present) that satisfied it,
 * never a single pass/fail. */
export interface RuleAlignment {
  rule_id: string;
  field: string;
  operator: StrategyOperator;
  weight: number;
  pass_rate: number;
  evaluated_candidate_count: number;
  reason: string;
}

export interface StrategyMatch {
  strategy_id: string;
  strategy_name: string;
  alignment_score: number;
  confidence: number;
  matched_rules: RuleAlignment[];
  failed_rules: RuleAlignment[];
  reasoning: string;
}

export interface StrategySummary {
  total_strategies: number;
  best_alignment: number;
  average_alignment: number;
  highest_confidence: number;
}

export interface StrategyEvaluationResult {
  request_id: string;
  evaluated_at: string;
  overall_alignment: number;
  best_strategy: string | null;
  strategy_matches: StrategyMatch[];
  summary: StrategySummary;
}

export interface ListStrategiesParams {
  page?: number;
  page_size?: number;
  sort?: "name" | "created_at" | "updated_at";
  direction?: "asc" | "desc";
  [key: string]: string | number | undefined;
}
