import { beforeEach, describe, expect, it } from "vitest";
import { restoreDefaultsFor, useSavedViewsStore } from "@/store/saved-views-store";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useNotificationFilterStore } from "@/store/notification-filter-store";

describe("saved-views-store", () => {
  beforeEach(() => {
    useSavedViewsStore.getState().clear();
    useDashboardLayoutStore.getState().resetLayout();
    usePreferencesStore.getState().resetAll();
    useNotificationFilterStore.getState().resetFilters();
  });

  it("saves a dashboard-layout view capturing the layout store's current state, and applying it restores that state", () => {
    useDashboardLayoutStore.getState().toggleCardVisibility("recent-activity");
    useDashboardLayoutStore.getState().cycleCardSize("user");

    useSavedViewsStore.getState().saveView("My layout", "dashboard-layout");
    const saved = useSavedViewsStore.getState().views[0];
    expect(saved?.kind).toBe("dashboard-layout");

    useDashboardLayoutStore.getState().resetLayout();
    expect(useDashboardLayoutStore.getState().hiddenCards).toEqual([]);

    useSavedViewsStore.getState().applyView(saved!.id);

    expect(useDashboardLayoutStore.getState().hiddenCards).toContain("recent-activity");
    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("md");
  });

  it("saves and applies a chart-defaults view", () => {
    usePreferencesStore.getState().setShowDataLabels(true);
    useSavedViewsStore.getState().saveView("Labels on", "chart-defaults");
    const saved = useSavedViewsStore.getState().views[0]!;

    usePreferencesStore.getState().setShowDataLabels(false);
    useSavedViewsStore.getState().applyView(saved.id);

    expect(usePreferencesStore.getState().charts.showDataLabels).toBe(true);
  });

  it("saves and applies a notification-filter view", () => {
    useNotificationFilterStore.getState().toggleDomain("alerts");
    useNotificationFilterStore.getState().setSearch("AAPL");
    useSavedViewsStore.getState().saveView("My filter", "notification-filter");
    const saved = useSavedViewsStore.getState().views[0]!;

    useNotificationFilterStore.getState().resetFilters();
    useSavedViewsStore.getState().applyView(saved.id);

    expect(useNotificationFilterStore.getState().domains).not.toContain("alerts");
    expect(useNotificationFilterStore.getState().search).toBe("AAPL");
  });

  it("deleteView removes exactly one view", () => {
    useSavedViewsStore.getState().saveView("A", "chart-defaults");
    useSavedViewsStore.getState().saveView("B", "chart-defaults");
    const [first, second] = useSavedViewsStore.getState().views;

    useSavedViewsStore.getState().deleteView(first!.id);

    expect(useSavedViewsStore.getState().views).toHaveLength(1);
    expect(useSavedViewsStore.getState().views[0]?.id).toBe(second!.id);
  });

  it("restoreDefaultsFor resets the live store for that kind without touching saved views", () => {
    usePreferencesStore.getState().setShowDataLabels(true);
    useSavedViewsStore.getState().saveView("Labels on", "chart-defaults");

    restoreDefaultsFor("chart-defaults");

    expect(usePreferencesStore.getState().charts.showDataLabels).toBe(false);
    expect(useSavedViewsStore.getState().views).toHaveLength(1);
  });
});
