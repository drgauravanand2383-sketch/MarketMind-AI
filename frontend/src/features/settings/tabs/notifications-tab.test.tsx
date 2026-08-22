import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationsTab } from "@/features/settings/tabs/notifications-tab";
import { usePreferencesStore } from "@/store/preferences-store";

describe("NotificationsTab", () => {
  beforeEach(() => {
    usePreferencesStore.getState().resetAll();
  });

  it("shows the v1.2 Priority 4 preferences at their defaults", () => {
    render(<NotificationsTab />);

    expect(screen.getByRole("checkbox", { name: "Group" })).toBeChecked();
    expect(screen.getByLabelText("Decision digest window, in minutes")).toHaveValue(5);
    expect(screen.getByRole("checkbox", { name: "Show toasts" })).toBeChecked();
  });

  it("toggling 'Group cross-portfolio notifications' off updates the store", async () => {
    const user = userEvent.setup();
    render(<NotificationsTab />);

    await user.click(screen.getByRole("checkbox", { name: "Group" }));

    expect(usePreferencesStore.getState().notifications.groupCrossPortfolioNotifications).toBe(false);
  });

  it("changing the decision digest window updates the store, clamped to [1, 30]", () => {
    render(<NotificationsTab />);
    const input = screen.getByLabelText("Decision digest window, in minutes");

    fireEvent.change(input, { target: { value: "12" } });

    expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(12);
  });

  it("a too-large decision digest window value is clamped to 30", () => {
    render(<NotificationsTab />);
    const input = screen.getByLabelText("Decision digest window, in minutes");

    fireEvent.change(input, { target: { value: "999" } });

    expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(30);
  });

  it("toggling 'Show realtime toasts' off updates the store", async () => {
    const user = userEvent.setup();
    render(<NotificationsTab />);

    await user.click(screen.getByRole("checkbox", { name: "Show toasts" }));

    expect(usePreferencesStore.getState().notifications.showRealtimeToasts).toBe(false);
  });

  it("resetting the notifications section restores the v1.2 Priority 4 defaults too", async () => {
    const user = userEvent.setup();
    usePreferencesStore.getState().setGroupCrossPortfolioNotifications(false);
    usePreferencesStore.getState().setShowRealtimeToasts(false);
    render(<NotificationsTab />);

    await user.click(screen.getByRole("button", { name: "Reset notifications" }));

    expect(usePreferencesStore.getState().notifications.groupCrossPortfolioNotifications).toBe(true);
    expect(usePreferencesStore.getState().notifications.showRealtimeToasts).toBe(true);
  });
});
