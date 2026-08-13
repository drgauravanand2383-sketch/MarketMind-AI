import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { CreateBacktestForm } from "@/features/historical-analysis/backtesting/create-backtest-form";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetBacktestingStore } from "@/test/msw/backtesting-store";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { useBacktestMarkersStore } from "@/store/backtest-markers-store";

const navigateSpy = vi.fn();
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, useNavigate: () => navigateSpy, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("CreateBacktestForm", () => {
  beforeEach(() => {
    navigateSpy.mockClear();
    resetBacktestingStore();
    resetDecisionCenterStore();
    useDecisionHistoryStore.setState({ entries: [] });
    useBacktestMarkersStore.setState({ markersByRunId: {} });
  });

  it("shows an empty state instead of the snapshot builder when no recommendation results exist this session", () => {
    renderWithQueryClient(<CreateBacktestForm />);
    expect(screen.getByText("No recommendation results this session yet")).toBeInTheDocument();
  });

  it("requires a name before submitting", async () => {
    useDecisionHistoryStore.setState({
      entries: [{ kind: "recommendations_generated", id: "h1", portfolioId: "wl-1", requestId: "rec-1", candidateCount: 3, occurredAt: "2026-01-15T00:00:00Z" }],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<CreateBacktestForm />);

    await user.click(screen.getByRole("button", { name: /run backtest/i }));

    expect(await screen.findByText("Name is required")).toBeInTheDocument();
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it("creates a backtest from a session-history snapshot and navigates to the run's detail page", async () => {
    useDecisionHistoryStore.setState({
      entries: [{ kind: "recommendations_generated", id: "h1", portfolioId: "wl-1", requestId: "rec-1", candidateCount: 3, occurredAt: "2026-01-15T00:00:00Z" }],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<CreateBacktestForm />);

    await user.type(screen.getByLabelText("Name"), "Q1 replay");
    await user.type(screen.getByLabelText("Start date"), "2026-01-01");
    await user.type(screen.getByLabelText("End date"), "2026-02-01");
    await user.selectOptions(screen.getByLabelText("Recommendation result"), "rec-1");

    await user.click(screen.getByRole("button", { name: /run backtest/i }));

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalled();
    });
    const [navigateArgs] = navigateSpy.mock.calls[0] as [{ to: string; params: { runId: string } }];
    expect(navigateArgs.to).toBe("/historical-analysis/backtests/$runId");
    const runId = navigateArgs.params.runId;
    expect(runId).toBeTruthy();

    expect(useDecisionHistoryStore.getState().entries[0]).toMatchObject({ kind: "backtest_run", runId, name: "Q1 replay" });
    expect(useBacktestMarkersStore.getState().markersByRunId[runId]).toHaveLength(1);
  });

  it("rejects an end date before the start date", async () => {
    useDecisionHistoryStore.setState({
      entries: [{ kind: "recommendations_generated", id: "h1", portfolioId: "wl-1", requestId: "rec-1", candidateCount: 3, occurredAt: "2026-01-15T00:00:00Z" }],
    });
    const user = userEvent.setup();
    renderWithQueryClient(<CreateBacktestForm />);

    await user.type(screen.getByLabelText("Name"), "Bad range");
    await user.type(screen.getByLabelText("Start date"), "2026-02-01");
    await user.type(screen.getByLabelText("End date"), "2026-01-01");
    await user.click(screen.getByRole("button", { name: /run backtest/i }));

    expect(await screen.findByText("Start date must not be after end date")).toBeInTheDocument();
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
