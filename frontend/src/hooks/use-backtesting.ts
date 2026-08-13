import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { backtestingApi } from "@/services/api/backtesting-api";
import { useBacktestMarkersStore, type BacktestMarker } from "@/store/backtest-markers-store";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { CreateBacktestRequest } from "@/types/backtesting";

export const backtestingKeys = {
  runs: () => ["backtests", "run"] as const,
  run: (runId: string) => [...backtestingKeys.runs(), runId] as const,
  results: () => ["backtests", "results"] as const,
  result: (runId: string) => [...backtestingKeys.results(), runId] as const,
};

/** `POST /backtests` creates the request and runs it fully synchronously
 * in one call (`app/backtesting/engine.py` — no background execution) —
 * `isPending` is the loading indicator, the same convention every prior
 * milestone's synchronous evaluate/generate endpoint established. */
export function useCreateBacktest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateBacktestRequest) => backtestingApi.create(body),
    onMutate: (body) => {
      notify("info", `Running backtest "${body.name}"...`);
    },
    onSuccess: (result, body) => {
      queryClient.setQueryData(backtestingKeys.result(result.request_id), result);
      notify(
        "success",
        `Backtest complete — portfolio ${result.portfolio_return >= 0 ? "+" : ""}${result.portfolio_return.toFixed(2)}% vs benchmark ${result.benchmark_return >= 0 ? "+" : ""}${result.benchmark_return.toFixed(2)}%.`,
      );
      useDecisionHistoryStore.getState().addEntry({
        kind: "backtest_run",
        id: result.request_id,
        runId: result.request_id,
        name: body.name,
        portfolioReturn: result.portfolio_return,
        benchmarkReturn: result.benchmark_return,
        occurredAt: result.generated_at,
      });
      // Captures the snapshot->recommendation/strategy/risk mapping this
      // frontend itself just submitted — the only place that mapping is
      // ever available (see `backtest-markers-store.ts`'s own docstring).
      const markers: BacktestMarker[] = (body.snapshots ?? []).map((snapshot) => ({
        timestamp: snapshot.timestamp,
        recommendationResultId: snapshot.recommendation_result_id,
        ...(snapshot.strategy_evaluation_id && { strategyEvaluationId: snapshot.strategy_evaluation_id }),
        ...(snapshot.risk_assessment_id && { riskAssessmentId: snapshot.risk_assessment_id }),
      }));
      useBacktestMarkersStore.getState().setMarkersForRun(result.request_id, markers);
    },
  });
}

export function useBacktestRun(runId: string) {
  return useQuery({
    queryKey: backtestingKeys.run(runId),
    queryFn: () => backtestingApi.getRun(runId),
    enabled: runId.length > 0,
  });
}

export function useBacktestResults(runId: string) {
  return useQuery({
    queryKey: backtestingKeys.result(runId),
    queryFn: () => backtestingApi.getResults(runId),
    enabled: runId.length > 0,
  });
}
