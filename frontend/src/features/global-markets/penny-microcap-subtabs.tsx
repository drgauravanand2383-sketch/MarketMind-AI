import type { ReactNode } from "react";
import { CATEGORY_DISPLAY_NAMES } from "@/features/global-markets/category-labels";
import { useRovingTablist } from "@/hooks/use-roving-tablist";
import { useGlobalMarketsStore } from "@/store/global-markets-store";
import type { ReportCategory } from "@/types/global-markets";

const SUB_TABS: { id: ReportCategory; label: string }[] = [
  { id: "INDIA_PENNY_STOCK", label: CATEGORY_DISPLAY_NAMES.INDIA_PENNY_STOCK },
  { id: "US_PENNY_STOCK", label: CATEGORY_DISPLAY_NAMES.US_PENNY_STOCK },
  { id: "CHINA_PENNY_STOCK", label: CATEGORY_DISPLAY_NAMES.CHINA_PENNY_STOCK },
  { id: "LOW_CAP_CRYPTO", label: CATEGORY_DISPLAY_NAMES.LOW_CAP_CRYPTO },
];

const SUB_TAB_IDS = SUB_TABS.map((tab) => tab.id);

/** A second, nested ARIA tablist — same shape as `GlobalMarketsTabs`,
 * one level down. Mirrors `features/settings/tabs/*`'s "sub-tab" nesting
 * convention. */
export function PennyMicrocapSubTabs(): ReactNode {
  const activeSubTab = useGlobalMarketsStore((state) => state.activePennySubTab);
  const setActivePennySubTab = useGlobalMarketsStore((state) => state.setActivePennySubTab);
  const { registerTabRef, handleTablistKeyDown } = useRovingTablist(SUB_TAB_IDS, activeSubTab, setActivePennySubTab);

  return (
    <div
      role="tablist"
      aria-label="Penny and micro-cap categories"
      onKeyDown={handleTablistKeyDown}
      className="flex flex-wrap gap-1"
    >
      {SUB_TABS.map((tab, index) => {
        const isActive = tab.id === activeSubTab;
        return (
          <button
            key={tab.id}
            ref={registerTabRef(index)}
            type="button"
            role="tab"
            id={`penny-microcap-subtab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`penny-microcap-subtabpanel-${tab.id}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => {
              setActivePennySubTab(tab.id);
            }}
            className={
              isActive
                ? "rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white"
                : "rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
