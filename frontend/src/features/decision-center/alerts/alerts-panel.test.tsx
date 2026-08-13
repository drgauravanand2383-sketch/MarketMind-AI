import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AlertsPanel } from "@/features/decision-center/alerts/alerts-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildAlert, buildSignalResult } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { signalResultStore } from "@/test/msw/handlers";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

describe("AlertsPanel", () => {
  beforeEach(() => {
    signalResultStore.reset();
    useDecisionHistoryStore.setState({ entries: [] });
    resetDecisionCenterStore({
      alerts: [buildAlert({ id: "alert-seed-1", ticker: "AAPL", priority: "HIGH", status: "GENERATED" })],
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
  });

  it("prompts to evaluate a signal first when no Signals-tab evaluation has run this session", () => {
    renderWithQueryClient(<AlertsPanel portfolioId="wl-1" />);
    expect(screen.getByText("Evaluate a signal first")).toBeInTheDocument();
  });

  it("lists the already-seeded alerts with a priority badge", async () => {
    renderWithQueryClient(<AlertsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });

  it("evaluates alerts chained from the most recent Signals-tab result and shows them", async () => {
    const user = userEvent.setup();
    const resultId = signalResultStore.put({
      signals: [buildSignalResult({ ticker: "MSFT", confidence: 90 })],
      evaluated: 1,
      triggered: 1,
      average_score: 90,
      summary: "1 of 1 triggered.",
    });
    useDecisionHistoryStore.getState().addEntry({ kind: "signals_evaluated", id: "e1", resultId, definitionId: "def-1", triggeredCount: 1, occurredAt: "2026-01-01T00:00:00Z" });

    renderWithQueryClient(<AlertsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Evaluate alerts" })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: "Evaluate alerts" }));

    await waitFor(() => {
      expect(screen.getByText(/MSFT/)).toBeInTheDocument();
    });
  });

  it("filters alerts by priority", async () => {
    resetDecisionCenterStore({
      alerts: [buildAlert({ id: "a1", ticker: "AAPL", priority: "HIGH" }), buildAlert({ id: "a2", ticker: "MSFT", priority: "LOW" })],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<AlertsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("Filter by priority"), "LOW");

    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });
});
