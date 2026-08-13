import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecentActivity } from "@/features/dashboard/recent-activity";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";
import { useSessionActivityStore } from "@/store/session-activity-store";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New HIGH alert — AAPL",
    summary: "RSI oversold.",
    occurredAt: "2026-01-15T12:00:00Z",
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

describe("RecentActivity", () => {
  beforeEach(() => {
    useRealtimeNotificationStore.setState({ entries: [] });
    useSessionActivityStore.setState({ recentResearch: [], recentScreeningRuns: [] });
  });

  it("shows an empty state before any real-time events or research have occurred this session", () => {
    render(<RecentActivity />);
    expect(screen.getByText("No recent activity")).toBeInTheDocument();
  });

  it("merges real-time notification entries with session research completions, newest first", () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ title: "New HIGH alert — AAPL", occurredAt: "2026-01-15T12:00:00Z" })],
    });
    useSessionActivityStore.setState({
      recentResearch: [{ requestId: "req-1", companyName: "Apple Inc.", ticker: "AAPL", matched: true, ranAt: "2026-01-15T11:00:00Z" }],
      recentScreeningRuns: [],
    });

    render(<RecentActivity />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("New HIGH alert — AAPL");
    expect(items[1]).toHaveTextContent("Research completed — Apple Inc.");
    expect(screen.getByText("This session")).toBeInTheDocument();
  });
});
