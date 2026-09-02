import type { ReactNode } from "react";
import { CATEGORY_DISPLAY_NAMES } from "@/features/global-markets/category-labels";
import { useRovingTablist } from "@/hooks/use-roving-tablist";
import { useGlobalMarketsStore, type GlobalMarketsTab } from "@/store/global-markets-store";

/** A synthetic "Top Picks" digest tab first, then the five main-category
 * tabs (labeled from `CATEGORY_DISPLAY_NAMES`), then one synthetic
 * "Penny & Micro-Cap" tab — "Top Picks" and "Penny & Micro-Cap" are
 * frontend groupings, not backend categories. */
const TABS: { id: GlobalMarketsTab; label: string }[] = [
  { id: "TOP_PICKS", label: "Top Picks" },
  { id: "INDIA_EQUITY", label: CATEGORY_DISPLAY_NAMES.INDIA_EQUITY },
  { id: "US_EQUITY", label: CATEGORY_DISPLAY_NAMES.US_EQUITY },
  { id: "CHINA_EQUITY", label: CATEGORY_DISPLAY_NAMES.CHINA_EQUITY },
  { id: "FOREX", label: CATEGORY_DISPLAY_NAMES.FOREX },
  { id: "CRYPTO", label: CATEGORY_DISPLAY_NAMES.CRYPTO },
  { id: "PENNY_MICROCAP", label: "Penny & Micro-Cap" },
];

const TAB_IDS = TABS.map((tab) => tab.id);

/** Same ARIA-tablist shape as `DecisionWorkspaceTabs` — `role="tablist"`/
 * `role="tab"`/`aria-selected`/`aria-controls`, keyboard nav via the
 * shared `useRovingTablist` hook. */
export function GlobalMarketsTabs(): ReactNode {
  const activeTab = useGlobalMarketsStore((state) => state.activeTab);
  const setActiveTab = useGlobalMarketsStore((state) => state.setActiveTab);
  const { registerTabRef, handleTablistKeyDown } = useRovingTablist(TAB_IDS, activeTab, setActiveTab);

  return (
    <div
      role="tablist"
      aria-label="Global Markets categories"
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
            id={`global-markets-tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`global-markets-tabpanel-${tab.id}`}
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
