import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RealtimeSummaryCards } from "@/features/dashboard/realtime-summary-cards";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New alert",
    summary: "Something happened.",
    occurredAt: "2026-01-15T12:00:00Z",
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

describe("RealtimeSummaryCards", () => {
  beforeEach(() => {
    useRealtimeNotificationStore.setState({ entries: [] });
  });

  it("shows zero for both tallies before any events arrive", () => {
    render(<RealtimeSummaryCards />);
    expect(screen.getByText("Recommendations generated this session")).toBeInTheDocument();
    const counts = screen.getAllByText("0");
    expect(counts).toHaveLength(2);
  });

  it("tallies recommendation and alert domain entries separately from other domains", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({ domain: "recommendations" }),
        buildEntry({ domain: "recommendations" }),
        buildEntry({ domain: "alerts" }),
        buildEntry({ domain: "backtests" }),
      ],
    });

    render(<RealtimeSummaryCards />);

    expect(screen.getByText("2")).toBeInTheDocument(); // recommendations
    expect(screen.getByText("1")).toBeInTheDocument(); // alerts
  });
});
