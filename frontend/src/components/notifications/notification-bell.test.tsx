import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode; onClick?: () => void }) => <a href={props.to} onClick={props.onClick}>{props.children}</a> };
});

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New HIGH alert — AAPL",
    summary: "RSI oversold.",
    occurredAt: "2026-01-01T00:00:00Z",
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

describe("NotificationBell", () => {
  beforeEach(() => {
    useRealtimeNotificationStore.setState({ entries: [] });
  });

  it("shows no unread badge when there are zero notifications", () => {
    render(<NotificationBell />);
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("shows the unread count in the trigger's accessible name and badge", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ read: false }), buildEntry({ read: true })] });

    render(<NotificationBell />);

    expect(screen.getByRole("button", { name: "Notifications (1 unread)" })).toBeInTheDocument();
  });

  it("opens the dropdown, shows recent entries, and marking all read clears the badge", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a", title: "New HIGH alert — AAPL", read: false })] });
    const user = userEvent.setup();
    render(<NotificationBell />);

    await user.click(screen.getByRole("button", { name: "Notifications (1 unread)" }));

    expect(screen.getByText("New HIGH alert — AAPL")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark all read" }));

    expect(useRealtimeNotificationStore.getState().entries[0]?.read).toBe(true);
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("announces the unread count in a polite live region for screen reader users", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ read: false }), buildEntry({ read: false })] });

    render(<NotificationBell />);

    expect(screen.getByText("2 unread notifications")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry()] });
    const user = userEvent.setup();
    render(<NotificationBell />);
    await user.click(screen.getByRole("button", { name: /notifications/i }));
    expect(screen.getByRole("link", { name: "View all" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("link", { name: "View all" })).not.toBeInTheDocument();
  });
});
