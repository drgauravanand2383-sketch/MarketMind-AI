import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { NotificationCenterPage } from "@/features/notifications/notification-center-page";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";
import { useNotificationFilterStore } from "@/store/notification-filter-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: (props: { to: string; params?: Record<string, string>; children?: ReactNode; onClick?: () => void }) => {
      const href = props.params
        ? Object.entries(props.params).reduce((path, [key, value]) => path.replace(`$${key}`, value), props.to)
        : props.to;
      return (
        <a href={href} onClick={props.onClick}>
          {props.children}
        </a>
      );
    },
  };
});

const NOW = "2026-01-15T12:00:00Z";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New HIGH alert — AAPL",
    summary: "RSI oversold.",
    occurredAt: NOW,
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

describe("NotificationCenterPage", () => {
  beforeEach(() => {
    vi.setSystemTime(new Date(NOW));
    useRealtimeNotificationStore.setState({ entries: [] });
    useNotificationFilterStore.getState().resetFilters();
  });

  it("shows an empty state when there are no notifications at all", () => {
    render(<NotificationCenterPage />);
    expect(screen.getByText("No notifications yet this session")).toBeInTheDocument();
  });

  it("renders entries grouped by date, with a deep link for backtest entries and a plain button for alert entries", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({ id: "a", title: "New HIGH alert — AAPL", entityRef: { kind: "alert" } }),
        buildEntry({
          id: "b",
          domain: "backtests",
          eventType: "BACKTEST_COMPLETED",
          title: "Backtest complete",
          entityRef: { kind: "backtest", runId: "run-1" },
        }),
      ],
    });

    render(<NotificationCenterPage />);

    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Backtest complete/ })).toHaveAttribute("href", "/historical-analysis/backtests/run-1");
    expect(screen.getByRole("button", { name: /New HIGH alert/ })).toBeInTheDocument();
  });

  it("filters by domain", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", domain: "alerts", title: "Alert entry" }), buildEntry({ id: "b", domain: "health", title: "Health entry", entityRef: { kind: "health" } })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    // All domains start checked (no filter) — unchecking every domain
    // except "Health" isolates it.
    await user.click(screen.getByLabelText("Alerts"));
    await user.click(screen.getByLabelText("Backtests"));
    await user.click(screen.getByLabelText("Recommendations"));
    await user.click(screen.getByLabelText("Strategy"));
    await user.click(screen.getByLabelText("Explainability"));

    expect(screen.queryByText("Alert entry")).not.toBeInTheDocument();
    expect(screen.getByText("Health entry")).toBeInTheDocument();
  });

  it("filters by read status", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", title: "Unread entry", read: false }), buildEntry({ id: "b", title: "Read entry", read: true })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.selectOptions(screen.getByLabelText("Filter by read status"), "unread");

    expect(screen.getByText("Unread entry")).toBeInTheDocument();
    expect(screen.queryByText("Read entry")).not.toBeInTheDocument();
  });

  it("searches by title/summary text", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", title: "New HIGH alert — AAPL" }), buildEntry({ id: "b", title: "New HIGH alert — MSFT" })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.type(screen.getByLabelText("Search notifications"), "MSFT");

    expect(screen.queryByText("New HIGH alert — AAPL")).not.toBeInTheDocument();
    expect(screen.getByText("New HIGH alert — MSFT")).toBeInTheDocument();
  });

  it("shows the no-matches empty state when filters exclude everything", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ domain: "alerts" })] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByLabelText("Alerts"));

    expect(screen.getByText("No notifications match your filters")).toBeInTheDocument();
  });

  it("marks an entry read on click", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a", title: "Click me", read: false })] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByRole("button", { name: /Click me/ }));

    expect(useRealtimeNotificationStore.getState().entries[0]?.read).toBe(true);
  });

  it("clear empties the list", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry()] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(useRealtimeNotificationStore.getState().entries).toEqual([]);
  });
});
