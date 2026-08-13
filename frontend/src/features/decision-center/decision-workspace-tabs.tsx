import type { ReactNode } from "react";
import { useRovingTablist } from "@/hooks/use-roving-tablist";
import { useDecisionWorkspaceStore, type DecisionWorkspaceTab } from "@/store/decision-workspace-store";

const TABS: { id: DecisionWorkspaceTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "recommendations", label: "Recommendations" },
  { id: "strategy", label: "Strategy" },
  { id: "risk", label: "Risk" },
  { id: "signals", label: "Signals" },
  { id: "alerts", label: "Alerts" },
];

const TAB_IDS = TABS.map((tab) => tab.id);

/** A standard ARIA tablist — `role="tablist"`/`role="tab"`/
 * `aria-selected`/`aria-controls` wired to `id`s the active panel
 * matches via `role="tabpanel"`/`aria-labelledby`, so screen readers and
 * keyboard users get the same tab semantics as the visual layout.
 * ArrowLeft/ArrowRight/Home/End navigation comes from the shared
 * `useRovingTablist` hook (Milestone 9 audit fix). */
export function DecisionWorkspaceTabs(): ReactNode {
  const activeTab = useDecisionWorkspaceStore((state) => state.activeTab);
  const setActiveTab = useDecisionWorkspaceStore((state) => state.setActiveTab);
  const { registerTabRef, handleTablistKeyDown } = useRovingTablist(TAB_IDS, activeTab, setActiveTab);

  return (
    <div
      role="tablist"
      aria-label="Decision workspace sections"
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
            id={`decision-tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`decision-tabpanel-${tab.id}`}
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
  );
}
