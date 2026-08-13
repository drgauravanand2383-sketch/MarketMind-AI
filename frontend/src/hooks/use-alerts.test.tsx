import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { buildAlert, buildSignalResult } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useAlert, useAlertsList, useEvaluateAlerts } from "@/hooks/use-alerts";

describe("use-alerts", () => {
  beforeEach(() => {
    resetDecisionCenterStore({
      alerts: [buildAlert({ id: "alert-seed-1", ticker: "AAPL" })],
      alertRules: [
        {
          id: "rule-1",
          name: "High confidence",
          description: "",
          enabled: true,
          priority: "HIGH",
          conditions: [{ id: "c1", field: "confidence", operator: "GREATER_EQUAL", value: 70, enabled: true }],
          cooldown_minutes: 0,
          repeat_allowed: true,
          channels: ["IN_APP"],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("useAlertsList fetches the seeded alerts", async () => {
    const { result } = renderHookWithQueryClient(() => useAlertsList({ page: 1, page_size: 20, sort: "created_at", direction: "desc" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.data.some((a) => a.id === "alert-seed-1")).toBe(true);
  });

  it("useAlert fetches a single alert by id", async () => {
    const { result } = renderHookWithQueryClient(() => useAlert("alert-seed-1"));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.ticker).toBe("AAPL");
  });

  it("useEvaluateAlerts generates alerts for signals that satisfy an enabled rule, recording history", async () => {
    const { result } = renderHookWithQueryClient(() => useEvaluateAlerts());

    result.current.mutate({ signals: [buildSignalResult({ ticker: "MSFT", confidence: 90 })] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.generated).toBeGreaterThan(0);
    expect(useDecisionHistoryStore.getState().entries[0]?.kind).toBe("alerts_evaluated");
  });

  it("useEvaluateAlerts generates nothing for a signal that fails every rule", async () => {
    const { result } = renderHookWithQueryClient(() => useEvaluateAlerts());

    result.current.mutate({ signals: [buildSignalResult({ ticker: "TINY", confidence: 10 })] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.generated).toBe(0);
  });
});
