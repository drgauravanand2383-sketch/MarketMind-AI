import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { resetExplainabilityStore } from "@/test/msw/explainability-store";
import { resetBacktestingStore, createBacktest } from "@/test/msw/backtesting-store";
import { buildHistoricalSnapshot } from "@/test/msw/fixtures";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useExplainabilityResult, useGenerateExplanation } from "@/hooks/use-explainability";

describe("use-explainability", () => {
  beforeEach(() => {
    resetExplainabilityStore();
    resetBacktestingStore();
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("useGenerateExplanation with only the required recommendation id omits the optional sections", async () => {
    const { result } = renderHookWithQueryClient(() => useGenerateExplanation());

    result.current.mutate({ name: "Why AAPL", recommendation_result_id: "rec-1" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.recommendation_explanations).toHaveLength(1);
    expect(result.current.data?.strategy_explanations).toEqual([]);
    expect(result.current.data?.risk_explanation).toBeNull();
    expect(result.current.data?.performance_attribution).toBeNull();

    const historyEntry = useDecisionHistoryStore.getState().entries[0];
    expect(historyEntry?.kind).toBe("explainability_generated");
  });

  it("useGenerateExplanation unlocks strategy/risk/attribution sections only when their ids are supplied", async () => {
    const backtestResult = createBacktest({
      name: "Q1 replay",
      start_date: "2026-01-01",
      end_date: "2026-02-01",
      initial_capital: 100_000,
      benchmark: "SPY",
      snapshots: [buildHistoricalSnapshot()],
    });

    const { result } = renderHookWithQueryClient(() => useGenerateExplanation());
    result.current.mutate({
      name: "Full explanation",
      recommendation_result_id: "rec-1",
      strategy_evaluation_id: "strat-1",
      risk_assessment_id: "risk-1",
      backtest_run_id: backtestResult.request_id,
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.strategy_explanations.length).toBeGreaterThan(0);
    expect(result.current.data?.risk_explanation).not.toBeNull();
    expect(result.current.data?.performance_attribution?.portfolio_return).toBe(backtestResult.portfolio_return);
  });

  it("useExplainabilityResult re-fetches a generated explanation by request_id", async () => {
    const { result: generateResult } = renderHookWithQueryClient(() => useGenerateExplanation());
    generateResult.current.mutate({ name: "Why AAPL", recommendation_result_id: "rec-1" });
    await waitFor(() => {
      expect(generateResult.current.isSuccess).toBe(true);
    });
    const requestId = generateResult.current.data?.request_id ?? "";

    const { result } = renderHookWithQueryClient(() => useExplainabilityResult(requestId));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.request_id).toBe(requestId);
  });

  it("useExplainabilityResult 404s for an unknown request id", async () => {
    const { result } = renderHookWithQueryClient(() => useExplainabilityResult("no-such-request"));
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
