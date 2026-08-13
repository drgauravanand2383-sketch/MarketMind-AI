import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { strategyApi } from "@/services/api/strategy-api";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { EvaluateStrategyRequest, ListStrategiesParams } from "@/types/strategy";

export const strategyKeys = {
  lists: () => ["strategies", "list"] as const,
  list: (params: ListStrategiesParams) => [...strategyKeys.lists(), params] as const,
  results: () => ["strategies", "results"] as const,
  result: (id: string) => [...strategyKeys.results(), id] as const,
};

export function useStrategiesList(params: ListStrategiesParams) {
  return useQuery({
    queryKey: strategyKeys.list(params),
    queryFn: () => strategyApi.list(params),
  });
}

/** No WebSocket event drives strategy-evaluation progress (confirmed
 * against the real API surface) — the mutation's own `isPending` is the
 * loading indicator, same convention Milestone 4 established for
 * research/screening. */
export function useEvaluateStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EvaluateStrategyRequest) => strategyApi.evaluate(body),
    onSuccess: (result) => {
      queryClient.setQueryData(strategyKeys.result(result.request_id), result);
      notify(
        "success",
        result.best_strategy
          ? `Strategy evaluation complete — best match: ${result.best_strategy}.`
          : "Strategy evaluation complete.",
      );
      useDecisionHistoryStore.getState().addEntry({
        kind: "strategy_evaluated",
        id: result.request_id,
        requestId: result.request_id,
        bestStrategy: result.best_strategy,
        occurredAt: result.evaluated_at,
      });
    },
  });
}

export function useStrategyEvaluationResult(resultId: string) {
  return useQuery({
    queryKey: strategyKeys.result(resultId),
    queryFn: () => strategyApi.getResult(resultId),
    enabled: resultId.length > 0,
  });
}
