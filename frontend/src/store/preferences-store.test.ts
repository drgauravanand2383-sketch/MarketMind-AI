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
});
