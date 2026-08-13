import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ExplainabilityComparePage } from "@/features/historical-analysis/comparison/explainability-compare-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetExplainabilityStore, seedExplainabilityResult } from "@/test/msw/explainability-store";
import { buildExplainabilityResult } from "@/test/msw/fixtures";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ExplainabilityComparePage", () => {
  beforeEach(() => {
    resetExplainabilityStore();
    useComparisonStore.setState({ backtestRunIds: [], explainabilityRequestIds: [] });
  });

  it("shows an empty state until two reports are selected", () => {
    useComparisonStore.setState({ explainabilityRequestIds: ["exp-1"] });
    renderWithQueryClient(<ExplainabilityComparePage />);
    expect(screen.getByText("Select two explainability reports to compare")).toBeInTheDocument();
  });

  it("highlights differing fields between the two selected reports", async () => {
    seedExplainabilityResult(buildExplainabilityResult({ request_id: "exp-1", overall_summary: "Summary A" }));
    seedExplainabilityResult(buildExplainabilityResult({ request_id: "exp-2", overall_summary: "Summary B" }));
    useComparisonStore.setState({ explainabilityRequestIds: ["exp-1", "exp-2"] });

    renderWithQueryClient(<ExplainabilityComparePage />);

    expect(await screen.findByText("Summary A")).toBeInTheDocument();
    expect(screen.getByText("Summary B")).toBeInTheDocument();
    const summaryRow = screen.getByText("Overall summary").closest("tr");
    expect(summaryRow?.className).toContain("bg-amber-50");
    const recRow = screen.getByText("Recommendation explanations").closest("tr");
    expect(recRow?.className).not.toContain("bg-amber-50");
  });

  it("clears the comparison selection", async () => {
    seedExplainabilityResult(buildExplainabilityResult({ request_id: "exp-1" }));
    seedExplainabilityResult(buildExplainabilityResult({ request_id: "exp-2" }));
    useComparisonStore.setState({ explainabilityRequestIds: ["exp-1", "exp-2"] });
    const user = userEvent.setup();
    renderWithQueryClient(<ExplainabilityComparePage />);
    await screen.findByRole("button", { name: "Clear selection" });

    await user.click(screen.getByRole("button", { name: "Clear selection" }));

    expect(useComparisonStore.getState().explainabilityRequestIds).toEqual([]);
  });
});
