import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { buildMarketDataSnapshot, buildSignalDefinition } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { useEvaluateSignals, useSignalDefinitionsList, useSignalResult } from "@/hooks/use-signals";

describe("use-signals", () => {
  beforeEach(() => {
    resetDecisionCenterStore({
      signalDefinitions: [
        buildSignalDefinition({
          id: "def-1",
          name: "High Price",
          conditions: [{ id: "c1", field: "quote.price", operator: "GREATER_THAN", value: 100, weight: 1, group: null, enabled: true }],
        }),
      ],
    });
  });

  it("useSignalDefinitionsList fetches the seeded definitions", async () => {
    const { result } = renderHookWithQueryClient(() => useSignalDefinitionsList({ page: 1, page_size: 20, sort: "name", direction: "asc" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.data).toHaveLength(1);
  });

  it("useEvaluateSignals evaluates snapshots against a definition's conditions", async () => {
    const { result } = renderHookWithQueryClient(() => useEvaluateSignals());

    result.current.mutate({
      definition_id: "def-1",
      snapshots: [buildMarketDataSnapshot({ ticker: "AAPL", quote: { ticker: "AAPL", price: 150, timestamp: "2026-01-01T00:00:00Z" } })],
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.batch_result.signals[0]?.triggered).toBe(true);
  });

  it("useEvaluateSignals correctly reports a non-triggered result when the condition fails", async () => {
    const { result } = renderHookWithQueryClient(() => useEvaluateSignals());

    result.current.mutate({
      definition_id: "def-1",
      snapshots: [buildMarketDataSnapshot({ ticker: "TINY", quote: { ticker: "TINY", price: 10, timestamp: "2026-01-01T00:00:00Z" } })],
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.batch_result.signals[0]?.triggered).toBe(false);
  });

  it("useSignalResult re-fetches a cached evaluation by result_id", async () => {
    const { result: evalResult } = renderHookWithQueryClient(() => useEvaluateSignals());
    evalResult.current.mutate({ definition_id: "def-1", snapshots: [buildMarketDataSnapshot()] });
    await waitFor(() => {
      expect(evalResult.current.isSuccess).toBe(true);
    });
    const resultId = evalResult.current.data?.result_id ?? "";

    const { result } = renderHookWithQueryClient(() => useSignalResult(resultId));
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.result_id).toBe(resultId);
  });
});
