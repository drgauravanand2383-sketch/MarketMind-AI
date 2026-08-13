import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BacktestDetailPage } from "@/features/historical-analysis/backtesting/backtest-detail-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetBacktestingStore, seedBacktest } from "@/test/msw/backtesting-store";
import { buildBacktestPeriod, buildBacktestResult, buildBacktestRun } from "@/test/msw/fixtures";
import { useComparisonStore } from "@/store/comparison-store";
import { useBacktestMarkersStore } from "@/store/backtest-markers-store";
import { useHistoricalAnalysisUiStore } from "@/store/historical-analysis-ui-store";

describe("BacktestDetailPage", () => {
  beforeEach(() => {
    resetBacktestingStore();
    useComparisonStore.setState({ backtestRunIds: [], explainabilityRequestIds: [] });
    useBacktestMarkersStore.setState({ markersByRunId: {} });
    useHistoricalAnalysisUiStore.setState({ timelineMetric: "both", periodsSearch: "", chartPreferences: { showDataLabels: false } });
  });

  it("shows summary metrics, periods table, and timeline for a fetched run", async () => {
    seedBacktest(
      buildBacktestRun({
        request_id: "run-1",
        results: [
          buildBacktestPeriod({ timestamp: "2026-01-15T00:00:00Z", return_percent: 4, notes: "Rebalanced into tech" }),
          buildBacktestPeriod({ timestamp: "2026-02-15T00:00:00Z", return_percent: -1, notes: "Drawdown period" }),
        ],
      }),
      buildBacktestResult({ request_id: "run-1", portfolio_return: 3, benchmark_return: 1, excess_return: 2, total_periods: 2, successful_periods: 1, failed_periods: 1 }),
    );

    renderWithQueryClient(<BacktestDetailPage runId="run-1" />);

    expect(await screen.findByText("+3.00%", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("+1.00%")).toBeInTheDocument();
    expect(screen.getByText("1/2 (50%)")).toBeInTheDocument();
    expect(screen.getByText("Rebalanced into tech")).toBeInTheDocument();
    expect(screen.getByText("Drawdown period")).toBeInTheDocument();
    // `HistoricalTimeline` is lazy-loaded (Milestone 9 performance fix) —
    // its content, including this note, only appears once the dynamic
    // `import()` behind its `Suspense` boundary resolves.
    expect(await screen.findByText(/wasn't created in the current browser session/i, {}, { timeout: 3000 })).toBeInTheDocument();
    // Chart panels mount without throwing under jsdom (Recharts'
    // `ResponsiveContainer` renders at zero size in jsdom — asserting the
    // surrounding panel heading, not chart-internal SVG, per the M4/M5
    // convention documented in those milestones' chart components).
    expect(screen.getByRole("heading", { name: "Portfolio vs benchmark" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Drawdown curve" })).toBeInTheDocument();
  });

  it("shows amber-dot marker note when the run's snapshot markers were captured this session", async () => {
    seedBacktest(
      buildBacktestRun({ request_id: "run-2", results: [buildBacktestPeriod({ timestamp: "2026-01-15T00:00:00Z" })] }),
      buildBacktestResult({ request_id: "run-2" }),
    );
    useBacktestMarkersStore.setState({ markersByRunId: { "run-2": [{ timestamp: "2026-01-15T00:00:00Z", recommendationResultId: "rec-1" }] } });

    renderWithQueryClient(<BacktestDetailPage runId="run-2" />);

    expect(await screen.findByText(/Amber dots mark periods fed by a recommendation result/i)).toBeInTheDocument();
  });

  it("filters the periods table by note text", async () => {
    seedBacktest(
      buildBacktestRun({
        request_id: "run-3",
        results: [
          buildBacktestPeriod({ timestamp: "2026-01-15T00:00:00Z", notes: "Rebalanced into tech" }),
          buildBacktestPeriod({ timestamp: "2026-02-15T00:00:00Z", notes: "Drawdown period" }),
        ],
      }),
      buildBacktestResult({ request_id: "run-3" }),
    );
    const user = userEvent.setup();
    renderWithQueryClient(<BacktestDetailPage runId="run-3" />);
    await screen.findByText("Rebalanced into tech");

    await user.type(screen.getByPlaceholderText("Search period notes…"), "Drawdown");

    expect(screen.queryByText("Rebalanced into tech")).not.toBeInTheDocument();
    expect(screen.getByText("Drawdown period")).toBeInTheDocument();
  });

  it("toggles comparison selection", async () => {
    seedBacktest(buildBacktestRun({ request_id: "run-4" }), buildBacktestResult({ request_id: "run-4" }));
    const user = userEvent.setup();
    renderWithQueryClient(<BacktestDetailPage runId="run-4" />);
    await screen.findByRole("button", { name: "Add to comparison" });

    await user.click(screen.getByRole("button", { name: "Add to comparison" }));

    expect(useComparisonStore.getState().backtestRunIds).toEqual(["run-4"]);
    expect(screen.getByRole("button", { name: "Selected for comparison" })).toBeInTheDocument();
  });

  it("shows an error state for an unknown run id", async () => {
    renderWithQueryClient(<BacktestDetailPage runId="no-such-run" />);
    await waitFor(() => {
      expect(screen.getByText("Couldn't load this backtest")).toBeInTheDocument();
    });
  });
});
