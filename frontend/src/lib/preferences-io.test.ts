import { beforeEach, describe, expect, it } from "vitest";
import { buildPreferencesExport, importPreferencesFromJson, PREFERENCES_EXPORT_VERSION } from "@/lib/preferences-io";
import { usePreferencesStore } from "@/store/preferences-store";
import { useThemeStore } from "@/store/theme-store";
import { useUiStore } from "@/store/ui-store";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { useSavedViewsStore } from "@/store/saved-views-store";

describe("preferences-io", () => {
  beforeEach(() => {
    // `applyTheme("system")` (invoked by a successful import) reads
    // `window.matchMedia`, which jsdom doesn't implement — stub it, the
    // same gap `theme-toggle.test.tsx` never happened to exercise.
    if (typeof window.matchMedia !== "function") {
      window.matchMedia = (): MediaQueryList => ({ matches: false }) as MediaQueryList;
    }
    usePreferencesStore.getState().resetAll();
    useThemeStore.setState({ mode: "system" });
    useUiStore.setState({ sidebarCollapsed: false });
    useDashboardLayoutStore.getState().resetLayout();
    useSavedViewsStore.getState().clear();
  });

  it("buildPreferencesExport captures the current state of every relevant store", () => {
    usePreferencesStore.getState().setAccentColor("violet");
    useThemeStore.setState({ mode: "dark" });
    useUiStore.setState({ sidebarCollapsed: true });

    const exported = buildPreferencesExport();

    expect(exported.version).toBe(PREFERENCES_EXPORT_VERSION);
    expect(exported.theme.mode).toBe("dark");
    expect(exported.ui.sidebarCollapsed).toBe(true);
    expect(exported.preferences.appearance.accentColor).toBe("violet");
  });

  it("round-trips export -> import back to the same state", () => {
    usePreferencesStore.getState().setAccentColor("rose");
    usePreferencesStore.getState().setToastDurationMs(3_000);
    useDashboardLayoutStore.getState().toggleCardVisibility("recent-activity");
    const json = JSON.stringify(buildPreferencesExport());

    usePreferencesStore.getState().resetAll();
    useDashboardLayoutStore.getState().resetLayout();

    const result = importPreferencesFromJson(json);

    expect(result.success).toBe(true);
    expect(usePreferencesStore.getState().appearance.accentColor).toBe("rose");
    expect(usePreferencesStore.getState().notifications.toastDurationMs).toBe(3_000);
    expect(useDashboardLayoutStore.getState().hiddenCards).toContain("recent-activity");
  });

  it("round-trips the Milestone 15 market/news/decisions notification domains", () => {
    usePreferencesStore.getState().toggleNotificationCategory("market");
    const json = JSON.stringify(buildPreferencesExport());
    usePreferencesStore.getState().resetAll();

    const result = importPreferencesFromJson(json);

    expect(result.success).toBe(true);
    expect(usePreferencesStore.getState().notifications.enabledCategories).not.toContain("market");
    expect(usePreferencesStore.getState().notifications.enabledCategories).toEqual(
      expect.arrayContaining(["news", "decisions"]),
    );
  });

  it("rejects invalid JSON entirely, writing nothing", () => {
    usePreferencesStore.getState().setAccentColor("green");

    const result = importPreferencesFromJson("{not valid json");

    expect(result.success).toBe(false);
    expect(usePreferencesStore.getState().appearance.accentColor).toBe("green");
  });

  it("rejects well-formed JSON that doesn't match the schema, writing nothing (rollback)", () => {
    usePreferencesStore.getState().setAccentColor("amber");

    const result = importPreferencesFromJson(JSON.stringify({ version: 1, theme: { mode: "not-a-real-mode" } }));

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error).toContain("preferences format");
    }
    // Rollback verified: the earlier setAccentColor("amber") is untouched.
    expect(usePreferencesStore.getState().appearance.accentColor).toBe("amber");
  });

  it("rejects a file with an unrecognized enum value inside an otherwise well-formed document", () => {
    const validExport = buildPreferencesExport();
    const tampered = { ...validExport, preferences: { ...validExport.preferences, appearance: { ...validExport.preferences.appearance, accentColor: "ultraviolet" } } };
    usePreferencesStore.getState().setDensity("compact");

    const result = importPreferencesFromJson(JSON.stringify(tampered));

    expect(result.success).toBe(false);
    expect(usePreferencesStore.getState().appearance.density).toBe("compact");
  });
});
