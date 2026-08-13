import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecommendationsPanel } from "@/features/decision-center/recommendations/recommendations-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";
import { useNotificationStore } from "@/store/notification-store";

describe("RecommendationsPanel", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
    useDecisionWorkspaceStore.setState({
      selectedPortfolioId: "",
      activeTab: "overview",
      activeRecommendationResultId: null,
      chartPreferences: { showDataLabels: false },
    });
  });

  it("shows a prompt to select a portfolio when none is given", () => {
    renderWithQueryClient(<RecommendationsPanel portfolioId="" />);
    expect(screen.getByText("Select a portfolio")).toBeInTheDocument();
  });

  it("renders the existing recommendation candidates and threads the result id into the workspace store", async () => {
    renderWithQueryClient(<RecommendationsPanel portfolioId="wl-1" />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    await waitFor(() => {
      expect(useDecisionWorkspaceStore.getState().activeRecommendationResultId).toBe("rec-1");
    });
  });

  it("selecting a candidate shows its detail panel", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<RecommendationsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "AAPL" }));

    const detailPanel = screen.getByText("Reasoning").closest("div");
    expect(detailPanel).not.toBeNull();
    expect(screen.getByText(/Strong evidence across screening and research/)).toBeInTheDocument();
  });

  it("filters the candidate list by recommendation type", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<RecommendationsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("Filter by recommendation type"), "WATCH");

    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("generates new recommendations from the form and shows a success notification", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<RecommendationsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Ticker"), "GOOG");
    await user.click(screen.getByRole("button", { name: /generate recommendations/i }));

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications.some((n) => /Recommendations generated/i.test(n.message))).toBe(true);
    });
  });

  it("renders the score-distribution chart panel once candidates are loaded", async () => {
    // jsdom has no real layout engine, so Recharts' `ResponsiveContainer`
    // doesn't render meaningful SVG internals in tests (same limitation
    // noted for adaptive/responsive layout throughout this project) —
    // this only asserts the chart's own panel mounts without crashing.
    renderWithQueryClient(<RecommendationsPanel portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Score distribution" })).toBeInTheDocument();
  });
});
