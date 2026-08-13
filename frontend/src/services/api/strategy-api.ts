import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type { EvaluateStrategyRequest, InvestmentStrategy, ListStrategiesParams, StrategyEvaluationResult } from "@/types/strategy";

/** Thin wrappers over `/api/v1/strategies/*`. This milestone only
 * *consumes* strategies (list + evaluate) — no create/edit/delete UI
 * exists, so those endpoints aren't wrapped here (the spec's Strategy
 * Evaluation section is display-only: best match, alignment, matched/
 * failed rules, comparison). */
export const strategyApi = {
  list: async (params: ListStrategiesParams = {}): Promise<PaginatedResponse<InvestmentStrategy>> => {
    return apiClient.get<PaginatedResponse<InvestmentStrategy>>(`/strategies${buildQueryString(params)}`);
  },

  /** Evaluates every strategy in `strategy_ids` (or every strategy, if
   * empty) against an already-computed `RecommendationResult` in one
   * call — ranked `strategy_matches` come back precomputed, so this is
   * also how "strategy comparison" is served, not a separate endpoint. */
  evaluate: async (body: EvaluateStrategyRequest): Promise<StrategyEvaluationResult> => {
    const response = await apiClient.post<SuccessResponse<StrategyEvaluationResult>>("/strategies/evaluate", body);
    return response.data;
  },

  getResult: async (resultId: string): Promise<StrategyEvaluationResult> => {
    const response = await apiClient.get<SuccessResponse<StrategyEvaluationResult>>(
      `/strategies/results/${encodeURIComponent(resultId)}`,
    );
    return response.data;
  },
};
