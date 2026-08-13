import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { notify, useNotificationStore } from "@/store/notification-store";

describe("notification-store", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("adds a notification and dismisses it after the default duration", () => {
    vi.useFakeTimers();
    notify("success", "Saved.");

    expect(useNotificationStore.getState().notifications).toHaveLength(1);

    vi.advanceTimersByTime(6_000);

    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("reuses an existing notification instead of stacking an identical one", () => {
    const firstId = notify("error", "Network error.", { durationMs: 0 });
    const secondId = notify("error", "Network error.", { durationMs: 0 });

    expect(secondId).toBe(firstId);
    expect(useNotificationStore.getState().notifications).toHaveLength(1);
  });

  it("dismiss() removes a specific notification", () => {
    const id = notify("info", "Heads up.", { durationMs: 0 });

    useNotificationStore.getState().dismiss(id);

    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("a durationMs of 0 never auto-dismisses", () => {
    vi.useFakeTimers();
    notify("warning", "Careful.", { durationMs: 0 });

    vi.advanceTimersByTime(60_000);

    expect(useNotificationStore.getState().notifications).toHaveLength(1);
  });

  it("pinned: true never auto-dismisses, same as durationMs: 0", () => {
    vi.useFakeTimers();
    notify("error", "Connection failed.", { pinned: true });

    vi.advanceTimersByTime(60_000);

    expect(useNotificationStore.getState().notifications).toHaveLength(1);
  });

  it("pinned overrides a conflicting durationMs", () => {
    vi.useFakeTimers();
    notify("error", "Connection failed.", { pinned: true, durationMs: 100 });

    vi.advanceTimersByTime(100);

    expect(useNotificationStore.getState().notifications).toHaveLength(1);
  });
});
