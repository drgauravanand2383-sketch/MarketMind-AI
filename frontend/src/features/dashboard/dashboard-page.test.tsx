import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { DashboardPage } from "@/features/dashboard/dashboard-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { testUser } from "@/test/msw/fixtures";
import { installFakeWebSocket } from "@/test/mock-websocket";
import { useAuthStore } from "@/store/auth-store";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";
import { useSessionActivityStore } from "@/store/session-activity-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ to, children }: { to: string; children?: ReactNode }) => <a href={to}>{children}</a>,
  };
});

describe("DashboardPage", () => {
  beforeEach(() => {
    installFakeWebSocket();
    useAuthStore.setState({
      status: "authenticated",
      user: { ...testUser, permissions: ["watchlist:read", "portfolio:read"] },
    });
    useRealtimeNotificationStore.setState({ entries: [] });
    useSessionActivityStore.setState({ recentResearch: [], recentScreeningRuns: [] });
    useDashboardLayoutStore.getState().resetLayout();
    useDashboardLayoutStore.setState({ isCustomizing: false });
  });

  it("shows the signed-in user's info", () => {
    renderWithQueryClient(<DashboardPage />);

    expect(screen.getByText(testUser.display_name ?? testUser.username)).toBeInTheDocument();
    expect(screen.getByText(testUser.email)).toBeInTheDocument();
  });

  it("resolves API connectivity to CONNECTED once the mocked health endpoint responds", async () => {
    renderWithQueryClient(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getAllByText("CONNECTED").length).toBeGreaterThan(0);
    });
  });

  it("only shows quick-nav cards for domains the user has permission for", () => {
    renderWithQueryClient(<DashboardPage />);

    expect(screen.getByText("Watchlists")).toBeInTheDocument();
    // "Decision Center" is the Milestone 5 nav item gated by
    // `portfolio:read` — it folded the old separate "Recommendations"
    // and "Risk" M2-era nav items into one.
    expect(screen.getByText("Decision Center")).toBeInTheDocument();
    expect(screen.queryByText("Backtesting")).not.toBeInTheDocument();
    expect(screen.queryByText("Screening")).not.toBeInTheDocument();
  });

  it("hides the Today's Global Markets card from a user without global_markets:read", () => {
    renderWithQueryClient(<DashboardPage />);

    expect(screen.queryByRole("heading", { level: 2, name: "Today's Global Markets" })).not.toBeInTheDocument();
  });

  it("shows the Today's Global Markets card once the user has global_markets:read", async () => {
    useAuthStore.setState({
      status: "authenticated",
      user: { ...testUser, permissions: ["watchlist:read", "portfolio:read", "global_markets:read"] },
    });

    renderWithQueryClient(<DashboardPage />);

    expect(await screen.findByRole("heading", { level: 2, name: "Today's Global Markets" })).toBeInTheDocument();
  });

  it("shows an empty state for recent activity before any real-time events or research have occurred this session", () => {
    renderWithQueryClient(<DashboardPage />);

    expect(screen.getByText("No recent activity")).toBeInTheDocument();
  });

  it("gives the Recent activity card its own h2 panel title, matching every other card, with no heading skip", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        {
          id: "entry-1",
          eventType: "ALERT_GENERATED",
          domain: "alerts",
          priority: "HIGH",
          title: "New HIGH alert — AAPL",
          summary: "RSI oversold.",
          occurredAt: "2026-01-15T12:00:00Z",
          read: false,
          entityRef: { kind: "alert" },
        },
      ],
    });
    renderWithQueryClient(<DashboardPage />);

    expect(screen.getByRole("heading", { level: 2, name: "Recent activity" })).toBeInTheDocument();
  });

  it("Customize dashboard reveals per-card controls; hiding a card moves it into the Hidden cards list", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DashboardPage />);
    expect(screen.queryByRole("button", { name: "Hide Account" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Customize dashboard" }));

    expect(screen.getByRole("button", { name: "Hide Account" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide Account" }));

    expect(useDashboardLayoutStore.getState().hiddenCards).toContain("user");
    expect(screen.getByText("Hidden cards")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show Account" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show Account" }));
    expect(useDashboardLayoutStore.getState().hiddenCards).not.toContain("user");
  });

  it("Customize dashboard's size-cycle button changes a card's recorded size", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DashboardPage />);
    await user.click(screen.getByRole("button", { name: "Customize dashboard" }));

    await user.click(screen.getByRole("button", { name: /Change Account size/ }));

    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("md");
  });
});
