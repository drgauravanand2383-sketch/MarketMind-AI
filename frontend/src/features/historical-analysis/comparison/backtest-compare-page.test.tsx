import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { BacktestComparePage } from "@/features/historical-analysis/comparison/backtest-compare-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetBacktestingStore, seedBacktest } from "@/test/msw/backtesting-store";
import { buildBacktestResult, buildBacktestRun } from "@/test/msw/fixtures";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("BacktestComparePage", () => {
  beforeEach(() => {
    resetBacktestingStore();
    useComparisonStore.setState({ backtestRunIds: [], explainabilityRequestIds: [] });
  });

  it("shows an empty state until two backtests are selected", () => {
    useComparisonStore.setState({ backtestRunIds: ["run-1"] });
    renderWithQueryClient(<BacktestComparePage />);
    expect(screen.getByText("Select two backtests to compare")).toBeInTheDocument();
  });

  it("highlights differing fields between the two selected backtests", async () => {
    seedBacktest(buildBacktestRun({ request_id: "run-1" }), buildBacktestResult({ request_id: "run-1", portfolio_return: 4, max_drawdown: 3.2 }));
    seedBacktest(buildBacktestRun({ request_id: "run-2" }), buildBacktestResult({ request_id: "run-2", portfolio_return: 8, max_drawdown: 3.2 }));
    useComparisonStore.setState({ backtestRunIds: ["run-1", "run-2"] });

    renderWithQueryClient(<BacktestComparePage />);

    expect(await screen.findByText("+4.00%")).toBeInTheDocument();
    expect(screen.getByText("+8.00%")).toBeInTheDocument();
    const drawdownRow = screen.getByText("Max drawdown").closest("tr");
    expect(drawdownRow?.className).not.toContain("bg-amber-50");
    const returnRow = screen.getByText("Portfolio return").closest("tr");
    expect(returnRow?.className).toContain("bg-amber-50");
  });

  it("clears the comparison selection", async () => {
    seedBacktest(buildBacktestRun({ request_id: "run-1" }), buildBacktestResult({ request_id: "run-1" }));
    seedBacktest(buildBacktestRun({ request_id: "run-2" }), buildBacktestResult({ request_id: "run-2" }));
    useComparisonStore.setState({ backtestRunIds: ["run-1", "run-2"] });
    const user = userEvent.setup();
    renderWithQueryClient(<BacktestComparePage />);
    await screen.findByRole("button", { name: "Clear selection" });

    await user.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(useComparisonStore.getState().backtestRunIds).toEqual([]);
  });
});
