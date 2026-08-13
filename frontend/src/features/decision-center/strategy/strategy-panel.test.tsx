import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrategyPanel } from "@/features/decision-center/strategy/strategy-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildInvestmentStrategy } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

describe("StrategyPanel", () => {
  beforeEach(() => {
    resetDecisionCenterStore({
      strategies: [buildInvestmentStrategy({ id: "s1", name: "Momentum Growth" }), buildInvestmentStrategy({ id: "s2", name: "Value" })],
    });
    useDecisionWorkspaceStore.setState({
      selectedPortfolioId: "wl-1",
      activeTab: "strategy",
      activeRecommendationResultId: null,
      chartPreferences: { showDataLabels: false },
    });
  });

  it("disables Evaluate and explains why when no recommendation result is loaded yet", async () => {
    renderWithQueryClient(<StrategyPanel />);
    await waitFor(() => {
      expect(screen.getByText("Momentum Growth")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /evaluate strategies/i })).toBeDisabled();
    expect(screen.getByText(/Generate recommendations first/i)).toBeInTheDocument();
  });

  it("evaluates strategies once a recommendation result is active, ranking them in the comparison table", async () => {
    useDecisionWorkspaceStore.setState({ activeRecommendationResultId: "rec-1" });
    const user = userEvent.setup();
    renderWithQueryClient(<StrategyPanel />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /evaluate strategies/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /evaluate strategies/i }));

    await waitFor(() => {
      expect(screen.getByText("Best match")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Alignment by strategy" })).toBeInTheDocument();
  });

  it("selecting a strategy from the comparison table shows its matched/failed rules", async () => {
    useDecisionWorkspaceStore.setState({ activeRecommendationResultId: "rec-1" });
    const user = userEvent.setup();
    renderWithQueryClient(<StrategyPanel />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /evaluate strategies/i })).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: /evaluate strategies/i }));
    await waitFor(() => {
      expect(screen.getByText("Best match")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Momentum Growth" }));

    expect(screen.getByText("Matched rules")).toBeInTheDocument();
    expect(screen.getByText("Failed rules")).toBeInTheDocument();
  });
});
