import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { buildInvestmentStrategy } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useEvaluateStrategy, useStrategiesList, useStrategyEvaluationResult } from "@/hooks/use-strategy";

describe("use-strategy", () => {
  beforeEach(() => {
    resetDecisionCenterStore({ strategies: [buildInvestmentStrategy({ id: "s1", name: "Momentum Growth" }), buildInvestmentStrategy({ id: "s2", name: "Value" })] });
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("useStrategiesList fetches the seeded strategies", async () => {
    const { result } = renderHookWithQueryClient(() => useStrategiesList({ page: 1, page_size: 20, sort: "name", direction: "asc" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.data).toHaveLength(2);
  });

  it("useEvaluateStrategy evaluates and ranks strategies, recording history", async () => {
    const { result } = renderHookWithQueryClient(() => useEvaluateStrategy());

    result.current.mutate({ recommendation_result_id: "rec-1", strategy_ids: [] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.strategy_matches.length).toBeGreaterThan(0);
    expect(result.current.data?.best_strategy).toBeTruthy();
    expect(useDecisionHistoryStore.getState().entries[0]?.kind).toBe("strategy_evaluated");
  });

  it("useStrategyEvaluationResult re-fetches a cached evaluation by request_id", async () => {
    const { result: evalResult } = renderHookWithQueryClient(() => useEvaluateStrategy());
    evalResult.current.mutate({ recommendation_result_id: "rec-1" });
    await waitFor(() => {
      expect(evalResult.current.isSuccess).toBe(true);
    });
    const requestId = evalResult.current.data?.request_id ?? "";

    const { result } = renderHookWithQueryClient(() => useStrategyEvaluationResult(requestId));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.request_id).toBe(requestId);
  });
});
