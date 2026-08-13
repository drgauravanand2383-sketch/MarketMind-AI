import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { WorkspaceSettingsPage } from "@/features/settings/workspace-settings-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useSavedViewsStore } from "@/store/saved-views-store";
import { useUiStore } from "@/store/ui-store";
import { useThemeStore } from "@/store/theme-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("WorkspaceSettingsPage", () => {
  beforeEach(() => {
    usePreferencesStore.getState().resetAll();
    useDashboardLayoutStore.getState().resetLayout();
    useSavedViewsStore.getState().clear();
    useUiStore.setState({ sidebarCollapsed: false });
    useThemeStore.setState({ mode: "system" });
  });

  it("shows the Appearance tab by default with the 6-tab tablist", () => {
    renderWithQueryClient(<WorkspaceSettingsPage />);

    expect(screen.getByRole("tab", { name: "Appearance", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tables" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Charts" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Accessibility" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
  });

  it("ArrowRight moves both focus and selection to the next tab", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);

    screen.getByRole("tab", { name: "Appearance" }).focus();
    await user.keyboard("{ArrowRight}");

    const dashboardTab = screen.getByRole("tab", { name: "Dashboard" });
    expect(dashboardTab).toHaveAttribute("aria-selected", "true");
    expect(dashboardTab).toHaveFocus();
  });

  it("switches tabs and updates a preference on the Tables tab", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);

    await user.click(screen.getByRole("tab", { name: "Tables" }));
    expect(screen.getByRole("tab", { name: "Tables", selected: true })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Default table page size"), "50");

    expect(usePreferencesStore.getState().tables.defaultPageSize).toBe(50);
  });

  it("Dashboard tab moves a card and resets the layout", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);
    await user.click(screen.getByRole("tab", { name: "Dashboard" }));

    await user.click(screen.getByRole("button", { name: "Move Account down" }));
    expect(useDashboardLayoutStore.getState().cardOrder[1]).toBe("user");

    await user.click(screen.getByRole("button", { name: "Reset dashboard layout" }));
    expect(useDashboardLayoutStore.getState().cardOrder[0]).toBe("user");
  });

  it("Accessibility tab toggles high contrast and resets the section", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);
    await user.click(screen.getByRole("tab", { name: "Accessibility" }));

    await user.click(screen.getByLabelText("High contrast"));
    expect(usePreferencesStore.getState().accessibility.highContrast).toBe(true);

    await user.click(screen.getByRole("button", { name: "Reset accessibility" }));
    expect(usePreferencesStore.getState().accessibility.highContrast).toBe(false);
  });

  it("saves a chart-defaults saved view and applies it", async () => {
    usePreferencesStore.getState().setShowDataLabels(true);
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);

    await user.type(screen.getByLabelText("Name"), "Labels on");
    await user.selectOptions(screen.getByLabelText("Captures"), "chart-defaults");
    await user.click(screen.getByRole("button", { name: "Save current as…" }));

    expect(screen.getByText("Labels on")).toBeInTheDocument();

    usePreferencesStore.getState().setShowDataLabels(false);
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(usePreferencesStore.getState().charts.showDataLabels).toBe(true);
  });

  it("exports and re-imports preferences via the Import/export panel", async () => {
    usePreferencesStore.getState().setAccentColor("rose");
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);

    const file = new File([JSON.stringify({ not: "valid" })], "bad.json", { type: "application/json" });
    const input = screen.getByLabelText("Import preferences file");
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(/doesn't match/i);
    });
  });

  it("Reset all preferences requires confirmation before resetting", async () => {
    usePreferencesStore.getState().setAccentColor("green");
    const user = userEvent.setup();
    renderWithQueryClient(<WorkspaceSettingsPage />);

    await user.click(screen.getByRole("button", { name: "Reset all preferences" }));
    expect(screen.getByRole("dialog", { name: "Reset all preferences?" })).toBeInTheDocument();
    expect(usePreferencesStore.getState().appearance.accentColor).toBe("green");

    await user.click(screen.getByRole("button", { name: "Reset all" }));

    expect(usePreferencesStore.getState().appearance.accentColor).toBe("blue");
  });
});
