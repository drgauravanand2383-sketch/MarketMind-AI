import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ScreeningComparePage } from "@/features/screening/screening-compare-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildScreeningProfile, buildScreenResult } from "@/test/msw/fixtures";
import { screeningResultStore } from "@/test/msw/handlers";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ScreeningComparePage", () => {
  beforeEach(() => {
    resetScreeningStore([buildScreeningProfile({ id: "p1", name: "Large Cap" })]);
    screeningResultStore.reset();
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [] });
  });

  it("shows an empty state when fewer than 2 runs are selected", () => {
    renderWithQueryClient(<ScreeningComparePage />);
    expect(screen.getByText("Select at least two screening runs to compare")).toBeInTheDocument();
  });

  it("builds a per-ticker matrix across the selected runs and flags a disagreement", async () => {
    const resultIdA = screeningResultStore.put([
      "p1",
      [buildScreenResult({ ticker: "AAPL", passed: true }), buildScreenResult({ ticker: "MSFT", company_name: "Microsoft", passed: true })],
    ] as const);
    const resultIdB = screeningResultStore.put(["p1", [buildScreenResult({ ticker: "AAPL", passed: false })]] as const);
    useComparisonStore.setState({ researchRequestIds: [], screeningResultIds: [resultIdA, resultIdB] });

    renderWithQueryClient(<ScreeningComparePage />);

    await waitFor(() => {
      expect(screen.getAllByText("AAPL")).toHaveLength(1);
    });
    // AAPL passed in run A but failed in run B — the row should be flagged.
    const aaplRow = screen.getByText("AAPL").closest("tr");
    expect(aaplRow).toHaveClass("bg-amber-50");
    // MSFT was only screened in run A — run B's cell should say "Not screened".
    expect(screen.getByText("Not screened")).toBeInTheDocument();
  });
});
