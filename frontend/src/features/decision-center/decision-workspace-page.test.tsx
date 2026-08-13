import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { DecisionWorkspacePage } from "@/features/decision-center/decision-workspace-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { buildWatchlist } from "@/test/msw/fixtures";
import { useDecisionWorkspaceStore } from "@/store/decision-workspace-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("DecisionWorkspacePage", () => {
  beforeEach(() => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useDecisionWorkspaceStore.setState({
      selectedPortfolioId: "",
      activeTab: "overview",
      activeRecommendationResultId: null,
      chartPreferences: { showDataLabels: false },
    });
  });

  it("shows the portfolio's own name as the heading and defaults to the Overview tab", async () => {
    renderWithQueryClient(<DecisionWorkspacePage portfolioId="wl-1" />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Tech Growth" })).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  it("switches tabs via the ARIA tablist and updates the workspace store", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DecisionWorkspacePage portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("tab", { name: "Risk" }));

    expect(screen.getByRole("tab", { name: "Risk" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "false");
    expect(useDecisionWorkspaceStore.getState().activeTab).toBe("risk");
  });

  it("ArrowRight moves both focus and selection to the next tab", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DecisionWorkspacePage portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    });

    screen.getByRole("tab", { name: "Overview" }).focus();
    await user.keyboard("{ArrowRight}");

    const recommendationsTab = screen.getByRole("tab", { name: "Recommendations" });
    expect(recommendationsTab).toHaveAttribute("aria-selected", "true");
    expect(recommendationsTab).toHaveFocus();
    expect(useDecisionWorkspaceStore.getState().activeTab).toBe("recommendations");
  });

  it("Home and End jump to the first and last tab", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DecisionWorkspacePage portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    });

    screen.getByRole("tab", { name: "Overview" }).focus();
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Alerts" })).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  });

  it("every tab is reachable and renders its own tabpanel", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DecisionWorkspacePage portfolioId="wl-1" />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Signals" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("tab", { name: "Signals" }));
    expect(screen.getByRole("tabpanel")).toHaveAttribute("id", "decision-tabpanel-signals");

    await user.click(screen.getByRole("tab", { name: "Alerts" }));
    expect(screen.getByRole("tabpanel")).toHaveAttribute("id", "decision-tabpanel-alerts");
  });
});
