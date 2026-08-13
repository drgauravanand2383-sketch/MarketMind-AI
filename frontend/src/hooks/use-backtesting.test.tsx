import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { buildHistoricalSnapshot } from "@/test/msw/fixtures";
import { resetBacktestingStore } from "@/test/msw/backtesting-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useBacktestMarkersStore } from "@/store/backtest-markers-store";
import { useBacktestRun, useBacktestResults, useCreateBacktest } from "@/hooks/use-backtesting";

describe("use-backtesting", () => {
  beforeEach(() => {
    resetBacktestingStore();
    useDecisionHistoryStore.setState({ entries: [] });
    useBacktestMarkersStore.setState({ markersByRunId: {} });
  });

  it("useCreateBacktest runs a backtest, recording history and markers from the submitted snapshots", async () => {
    const { result } = renderHookWithQueryClient(() => useCreateBacktest());

    result.current.mutate({
      name: "Q1 replay",
      start_date: "2026-01-01",
      end_date: "2026-02-01",
      initial_capital: 100_000,
      benchmark: "SPY",
      replay_mode: "MONTHLY",
      snapshots: [buildHistoricalSnapshot({ timestamp: "2026-01-15T00:00:00Z", recommendation_result_id: "rec-1" })],
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.total_periods).toBe(1);
    const runId = result.current.data?.request_id ?? "";

    const historyEntry = useDecisionHistoryStore.getState().entries[0];
    expect(historyEntry?.kind).toBe("backtest_run");
    expect(historyEntry && "runId" in historyEntry ? historyEntry.runId : undefined).toBe(runId);

    const markers = useBacktestMarkersStore.getState().markersByRunId[runId];
    expect(markers).toHaveLength(1);
    expect(markers?.[0]?.recommendationResultId).toBe("rec-1");
  });

  it("useCreateBacktest with zero snapshots yields zero periods and no markers", async () => {
    const { result } = renderHookWithQueryClient(() => useCreateBacktest());

    result.current.mutate({
      name: "Empty replay",
      start_date: "2026-01-01",
      end_date: "2026-02-01",
      initial_capital: 100_000,
      benchmark: "SPY",
      snapshots: [],
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.total_periods).toBe(0);
    const runId = result.current.data?.request_id ?? "";
    expect(useBacktestMarkersStore.getState().markersByRunId[runId]).toEqual([]);
  });

  it("useBacktestRun and useBacktestResults fetch the created run by its request_id", async () => {
    const { result: createResult } = renderHookWithQueryClient(() => useCreateBacktest());
    createResult.current.mutate({
      name: "Q1 replay",
      start_date: "2026-01-01",
      end_date: "2026-02-01",
      initial_capital: 100_000,
      benchmark: "SPY",
      snapshots: [buildHistoricalSnapshot()],
    });
    await waitFor(() => {
      expect(createResult.current.isSuccess).toBe(true);
    });
    const runId = createResult.current.data?.request_id ?? "";

    const { result: runResult } = renderHookWithQueryClient(() => useBacktestRun(runId));
    await waitFor(() => {
      expect(runResult.current.isSuccess).toBe(true);
    });
    expect(runResult.current.data?.results).toHaveLength(1);

    const { result: resultsResult } = renderHookWithQueryClient(() => useBacktestResults(runId));
    await waitFor(() => {
      expect(resultsResult.current.isSuccess).toBe(true);
    });
    expect(resultsResult.current.data?.request_id).toBe(runId);
  });

  it("useBacktestRun 404s for an unknown run id", async () => {
    const { result } = renderHookWithQueryClient(() => useBacktestRun("no-such-run"));
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
