import { useState, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { useRovingTablist } from "@/hooks/use-roving-tablist";
import { AccessibilityTab } from "@/features/settings/tabs/accessibility-tab";
import { AppearanceTab } from "@/features/settings/tabs/appearance-tab";
import { ChartsTab } from "@/features/settings/tabs/charts-tab";
import { DashboardTab } from "@/features/settings/tabs/dashboard-tab";
import { NotificationsTab } from "@/features/settings/tabs/notifications-tab";
import { ShortcutsTab } from "@/features/settings/tabs/shortcuts-tab";
import { TablesTab } from "@/features/settings/tabs/tables-tab";
import { ImportExportPanel } from "@/features/settings/import-export-panel";
import { ResetAllButton } from "@/features/settings/reset-all-button";
import { SavedViewsPanel } from "@/features/settings/saved-views-panel";

type SettingsTab = "appearance" | "dashboard" | "tables" | "charts" | "notifications" | "accessibility" | "shortcuts";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "appearance", label: "Appearance" },
  { id: "dashboard", label: "Dashboard" },
  { id: "tables", label: "Tables" },
  { id: "charts", label: "Charts" },
  { id: "notifications", label: "Notifications" },
  { id: "accessibility", label: "Accessibility" },
  { id: "shortcuts", label: "Shortcuts" },
];

const TAB_IDS = TABS.map((tab) => tab.id);

const TAB_CONTENT: Record<SettingsTab, ReactNode> = {
  appearance: <AppearanceTab />,
  dashboard: <DashboardTab />,
  tables: <TablesTab />,
  charts: <ChartsTab />,
  notifications: <NotificationsTab />,
  accessibility: <AccessibilityTab />,
  shortcuts: <ShortcutsTab />,
};

/**
 * Milestone 8's Workspace Settings page — originally 6 tabs matching
 * that milestone's spec exactly, an ARIA tablist (`role="tablist"`/
 * `role="tab"`/`aria-selected`/`aria-controls`), the same pattern
 * `DecisionWorkspaceTabs` (Milestone 5) established. Saved Views/
 * Import-Export/Reset-all are cross-cutting actions, not specific to one
 * tab, so they live in an always-visible header area instead of being
 * buried in an arbitrary tab. A 7th "Shortcuts" tab was added in
 * Milestone 9 for configuring keyboard shortcuts.
 */
export function WorkspaceSettingsPage(): ReactNode {
  const [activeTab, setActiveTab] = useState<SettingsTab>("appearance");
  const { registerTabRef, handleTablistKeyDown } = useRovingTablist(TAB_IDS, activeTab, setActiveTab);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Workspace settings</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Personalize how MarketMind AI looks and behaves — none of this changes recommendation logic or any investment
          data.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Saved views">
          <SavedViewsPanel />
        </Panel>
        <div className="flex flex-col gap-4">
          <Panel title="Import / export">
            <ImportExportPanel />
          </Panel>
          <Panel title="Reset">
            <ResetAllButton />
          </Panel>
        </div>
      </div>

      <div>
        <div
          role="tablist"
          aria-label="Workspace settings sections"
          onKeyDown={handleTablistKeyDown}
          className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800"
        >
          {TABS.map((tab, index) => {
            const isActive = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                ref={registerTabRef(index)}
                type="button"
                role="tab"
                id={`settings-tab-${tab.id}`}
                aria-selected={isActive}
                aria-controls={`settings-tabpanel-${tab.id}`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => {
                  setActiveTab(tab.id);
                }}
                className={
                  isActive
                    ? "border-b-2 border-brand-600 px-3 py-2 text-sm font-medium text-brand-700 dark:text-brand-400"
                    : "border-b-2 border-transparent px-3 py-2 text-sm font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                }
              >
                {tab.label}
              </button>
            );
          })}
        </div>
        <div id={`settings-tabpanel-${activeTab}`} role="tabpanel" aria-labelledby={`settings-tab-${activeTab}`} className="pt-4">
          {TAB_CONTENT[activeTab]}
        </div>
      </div>
    </div>
  );
}
