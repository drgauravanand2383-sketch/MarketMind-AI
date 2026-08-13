import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ExplainabilityResultPanel } from "@/features/historical-analysis/explainability/explainability-result-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildContributionBreakdown, buildExplainabilityResult } from "@/test/msw/fixtures";
import { useComparisonStore } from "@/store/comparison-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ExplainabilityResultPanel", () => {
  beforeEach(() => {
    useComparisonStore.setState({ backtestRunIds: [], explainabilityRequestIds: [] });
  });

  it("shows the recommendation explanation and 'not supplied' fallbacks for the omitted optional sections", () => {
    const result = buildExplainabilityResult({ request_id: "exp-1" });
    renderWithQueryClient(<ExplainabilityResultPanel result={result} />);

    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("Strong evidence across screening and research.")).toBeInTheDocument();
    expect(screen.getByText("No strategy evaluation was supplied for this explanation.")).toBeInTheDocument();
    expect(screen.getByText("No risk assessment was supplied for this explanation.")).toBeInTheDocument();
    expect(screen.getByText("No performance attribution")).toBeInTheDocument();
  });

  it("renders the strategy, risk, and performance attribution sections once populated", () => {
    const result = buildExplainabilityResult({
      request_id: "exp-2",
      strategy_explanations: [
        { strategy_name: "Momentum Growth", alignment_score: 78, matched_rules: [], failed_rules: [], weight_breakdown: [], summary: "Aligns well." },
      ],
      risk_explanation: {
        overall_risk_score: 42,
        category_breakdown: [],
        severity_breakdown: { MODERATE: 2 },
        exposure_breakdown: [{ sector: "Technology", country: null, industry: null, weight: 0.6, holding_count: 3 }],
        summary: "Moderate concentration risk in Technology.",
      },
      performance_attribution: {
        period: "2026-01-01 to 2026-02-01",
        portfolio_return: 4,
        benchmark_return: 1.5,
        excess_return: 2.5,
        contribution_breakdown: [buildContributionBreakdown()],
        summary: "Sector exposure contributed positively.",
      },
    });

    renderWithQueryClient(<ExplainabilityResultPanel result={result} />);

    expect(screen.getByText("Momentum Growth")).toBeInTheDocument();
    expect(screen.getByText("Aligns well.")).toBeInTheDocument();
    expect(screen.getByText("Moderate concentration risk in Technology.")).toBeInTheDocument();
    expect(screen.getByText("Period: 2026-01-01 to 2026-02-01")).toBeInTheDocument();
    expect(screen.getByText("+4.00%")).toBeInTheDocument();
    expect(screen.getByText("Sector exposure contributed positively.")).toBeInTheDocument();
  });

  it("toggles comparison selection and reveals the 'Compare selected' link once two are picked", async () => {
    const user = userEvent.setup();
    useComparisonStore.setState({ explainabilityRequestIds: ["other-request"] });
    const result = buildExplainabilityResult({ request_id: "exp-3" });
    renderWithQueryClient(<ExplainabilityResultPanel result={result} />);

    await user.click(screen.getByRole("button", { name: "Add to comparison" }));

    expect(useComparisonStore.getState().explainabilityRequestIds).toEqual(["other-request", "exp-3"]);
    expect(screen.getByRole("link", { name: "Compare selected (2)" })).toBeInTheDocument();
  });
});
