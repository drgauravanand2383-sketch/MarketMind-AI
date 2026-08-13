import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import type * as ReactRouterModule from "@tanstack/react-router";
import { HistoricalAnalysisLandingPage } from "@/features/historical-analysis/historical-analysis-landing-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("HistoricalAnalysisLandingPage", () => {
  beforeEach(() => {
    useDecisionHistoryStore.setState({ entries: [] });
  });

  it("shows entry points for Backtesting and Explainability, and an empty session history", () => {
    renderWithQueryClient(<HistoricalAnalysisLandingPage />);

    expect(screen.getByRole("heading", { name: "Historical Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run a backtest" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Generate an explanation" })).toBeInTheDocument();
    expect(screen.getByText("No historical analysis yet this session")).toBeInTheDocument();
  });

  it("lists backtest_run and explainability_generated history entries, ignoring Decision Center entries", () => {
    useDecisionHistoryStore.setState({
      entries: [
        { kind: "backtest_run", id: "h1", runId: "run-1", name: "Q1 replay", portfolioReturn: 4, benchmarkReturn: 1.5, occurredAt: "2026-02-01T00:05:00Z" },
        { kind: "explainability_generated", id: "h2", requestId: "exp-1", recommendationResultId: "rec-1", occurredAt: "2026-02-01T00:06:00Z" },
        { kind: "strategy_evaluated", id: "h3", requestId: "strat-1", bestStrategy: "Momentum Growth", occurredAt: "2026-02-01T00:07:00Z" },
      ],
    });

    renderWithQueryClient(<HistoricalAnalysisLandingPage />);

    expect(screen.getByText('Backtest "Q1 replay" — +4.00%')).toBeInTheDocument();
    expect(screen.getByText("Explanation generated")).toBeInTheDocument();
    expect(screen.queryByText(/Momentum Growth/)).not.toBeInTheDocument();
  });
});
