import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New alert",
    summary: "Something happened.",
    occurredAt: "2026-01-01T00:00:00Z",
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

/** Selects the stable `entries` array and filters in the component body
 * — exactly the pattern every consumer of this store must use (see the
 * store's own docstring) — as a regression test against the M6
 * `useSyncExternalStore` "getSnapshot should be cached" infinite-loop
 * footgun. */
function UnreadCount(): ReactNode {
  const entries = useRealtimeNotificationStore((state) => state.entries);
  const unread = entries.filter((entry) => !entry.read).length;
  return <span>{unread} unread</span>;
}

describe("realtime-notification-store", () => {
  it("addEntry prepends and caps at 200 entries", () => {
    useRealtimeNotificationStore.setState({ entries: [] });
    for (let i = 0; i < 205; i += 1) {
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: `entry-${String(i)}` }));
    }

    const entries = useRealtimeNotificationStore.getState().entries;
    expect(entries).toHaveLength(200);
    expect(entries[0]?.id).toBe("entry-204"); // newest first
  });

  it("markRead marks exactly one entry read", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a" }), buildEntry({ id: "b" })] });

    useRealtimeNotificationStore.getState().markRead("a");

    const entries = useRealtimeNotificationStore.getState().entries;
    expect(entries.find((e) => e.id === "a")?.read).toBe(true);
    expect(entries.find((e) => e.id === "b")?.read).toBe(false);
  });

  it("markAllRead marks every entry read", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a" }), buildEntry({ id: "b" })] });

    useRealtimeNotificationStore.getState().markAllRead();

    expect(useRealtimeNotificationStore.getState().entries.every((e) => e.read)).toBe(true);
  });

  it("clear empties the list", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry()] });

    useRealtimeNotificationStore.getState().clear();

    expect(useRealtimeNotificationStore.getState().entries).toEqual([]);
  });

  it("a component filtering `entries` in its body (not inside the selector) renders without an infinite-loop error", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ read: false }), buildEntry({ read: true })] });

    render(<UnreadCount />);

    expect(screen.getByText("1 unread")).toBeInTheDocument();
  });
});
