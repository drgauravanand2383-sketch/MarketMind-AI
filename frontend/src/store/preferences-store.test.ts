import { beforeEach, describe, expect, it } from "vitest";
import { usePreferencesStore } from "@/store/preferences-store";

function resetPreferencesStore(): void {
  usePreferencesStore.getState().resetAll();
  window.localStorage.clear();
}

describe("preferences-store", () => {
  beforeEach(() => {
    resetPreferencesStore();
  });

  it("persists appearance changes to localStorage", () => {
    usePreferencesStore.getState().setAccentColor("violet");
    usePreferencesStore.getState().setDensity("compact");

    const raw = window.localStorage.getItem("marketmind-preferences");
    expect(raw).toContain("violet");
    expect(raw).toContain("compact");
  });

  it("toggleNotificationCategory adds and removes a domain", () => {
    usePreferencesStore.getState().toggleNotificationCategory("alerts");
    expect(usePreferencesStore.getState().notifications.enabledCategories).not.toContain("alerts");

    usePreferencesStore.getState().toggleNotificationCategory("alerts");
    expect(usePreferencesStore.getState().notifications.enabledCategories).toContain("alerts");
  });

  it("resetSection resets only that section, leaving others untouched", () => {
    usePreferencesStore.getState().setAccentColor("rose");
    usePreferencesStore.getState().setToastDurationMs(1_000);

    usePreferencesStore.getState().resetSection("notifications");

    expect(usePreferencesStore.getState().notifications.toastDurationMs).toBe(6_000);
    expect(usePreferencesStore.getState().appearance.accentColor).toBe("rose");
  });

  it("resetAll restores every section to its default", () => {
    usePreferencesStore.getState().setAccentColor("green");
    usePreferencesStore.getState().setHighContrast(true);
    usePreferencesStore.getState().setDefaultPageSize(100);

    usePreferencesStore.getState().resetAll();

    expect(usePreferencesStore.getState().appearance.accentColor).toBe("blue");
    expect(usePreferencesStore.getState().accessibility.highContrast).toBe(false);
    expect(usePreferencesStore.getState().tables.defaultPageSize).toBe(20);
  });

  // --- v1.2 Priority 4: Notification & Intelligence Preferences -----------------------------------------------------------

  describe("v1.2 Priority 4 notification preferences", () => {
    it("defaults: grouping on, 5-minute digest window, toasts on", () => {
      const notifications = usePreferencesStore.getState().notifications;
      expect(notifications.groupCrossPortfolioNotifications).toBe(true);
      expect(notifications.decisionDigestWindowMinutes).toBe(5);
      expect(notifications.showRealtimeToasts).toBe(true);
    });

    it("setGroupCrossPortfolioNotifications toggles the flag", () => {
      usePreferencesStore.getState().setGroupCrossPortfolioNotifications(false);
      expect(usePreferencesStore.getState().notifications.groupCrossPortfolioNotifications).toBe(false);
    });

    it("setShowRealtimeToasts toggles the flag", () => {
      usePreferencesStore.getState().setShowRealtimeToasts(false);
      expect(usePreferencesStore.getState().notifications.showRealtimeToasts).toBe(false);
    });

    it("setDecisionDigestWindowMinutes accepts an in-range value unchanged", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(12);
      expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(12);
    });

    it("setDecisionDigestWindowMinutes clamps out-of-range values to [1, 30]", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(999);
      expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(30);

      usePreferencesStore.getState().setDecisionDigestWindowMinutes(0);
      expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(1);

      usePreferencesStore.getState().setDecisionDigestWindowMinutes(-5);
      expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(1);
    });

    it("setDecisionDigestWindowMinutes falls back to the default (5) on a non-numeric value", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(Number.NaN);
      expect(usePreferencesStore.getState().notifications.decisionDigestWindowMinutes).toBe(5);
    });

    it("resetSection('notifications') restores all 3 new fields to their defaults", () => {
      usePreferencesStore.getState().setGroupCrossPortfolioNotifications(false);
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(20);
      usePreferencesStore.getState().setShowRealtimeToasts(false);

      usePreferencesStore.getState().resetSection("notifications");

      const notifications = usePreferencesStore.getState().notifications;
      expect(notifications.groupCrossPortfolioNotifications).toBe(true);
      expect(notifications.decisionDigestWindowMinutes).toBe(5);
      expect(notifications.showRealtimeToasts).toBe(true);
    });

    it("rehydrating from a legacy blob (missing the 3 new fields) fills in safe defaults without disturbing other fields", async () => {
      window.localStorage.setItem(
        "marketmind-preferences",
        JSON.stringify({
          state: {
            notifications: {
              toastDurationMs: 3_000,
              defaultPinned: true,
              soundEnabled: false,
              desktopNotificationsEnabled: false,
              enabledCategories: ["alerts"],
            },
          },
          version: 0,
        }),
      );

      await usePreferencesStore.persist.rehydrate();

      const notifications = usePreferencesStore.getState().notifications;
      expect(notifications.toastDurationMs).toBe(3_000);
      expect(notifications.defaultPinned).toBe(true);
      expect(notifications.groupCrossPortfolioNotifications).toBe(true);
      expect(notifications.decisionDigestWindowMinutes).toBe(5);
      expect(notifications.showRealtimeToasts).toBe(true);
    });

    it("rehydrating from a corrupted blob (out-of-range window, wrong-typed booleans) recovers safely", async () => {
      window.localStorage.setItem(
        "marketmind-preferences",
        JSON.stringify({
          state: {
            notifications: {
              toastDurationMs: 6_000,
              defaultPinned: false,
              soundEnabled: false,
              desktopNotificationsEnabled: false,
              enabledCategories: ["alerts"],
              groupCrossPortfolioNotifications: "yes",
              decisionDigestWindowMinutes: -40,
              showRealtimeToasts: 1,
            },
          },
          version: 0,
        }),
      );

      await usePreferencesStore.persist.rehydrate();

      const notifications = usePreferencesStore.getState().notifications;
      expect(notifications.groupCrossPortfolioNotifications).toBe(true); // wrong type -> default
      expect(notifications.decisionDigestWindowMinutes).toBe(1); // out of range, clamped
      expect(notifications.showRealtimeToasts).toBe(true); // wrong type -> default
    });
  });
});
