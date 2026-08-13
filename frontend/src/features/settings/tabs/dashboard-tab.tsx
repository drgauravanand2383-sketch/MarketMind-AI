import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { getDashboardCard } from "@/features/dashboard/dashboard-card-registry";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import type { CardSize } from "@/types/preferences";

const SIZE_LABEL: Record<CardSize, string> = { sm: "Small", md: "Medium", lg: "Large" };

const CONTROL_BUTTON_CLASS =
  "rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800";

/**
 * A full management list for every registered dashboard card (visible
 * and hidden) — the same reorder/hide/resize actions the Dashboard
 * page's own "Customize dashboard" mode uses (`dashboard-layout-store.ts`),
 * presented here as a compact list rather than duplicating the grid-
 * based in-context editor.
 */
export function DashboardTab(): ReactNode {
  const cardOrder = useDashboardLayoutStore((state) => state.cardOrder);
  const hiddenCards = useDashboardLayoutStore((state) => state.hiddenCards);
  const cardSizes = useDashboardLayoutStore((state) => state.cardSizes);
  const moveCardUp = useDashboardLayoutStore((state) => state.moveCardUp);
  const moveCardDown = useDashboardLayoutStore((state) => state.moveCardDown);
  const toggleCardVisibility = useDashboardLayoutStore((state) => state.toggleCardVisibility);
  const cycleCardSize = useDashboardLayoutStore((state) => state.cycleCardSize);
  const resetLayout = useDashboardLayoutStore((state) => state.resetLayout);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Reorder, resize, or hide dashboard cards. Changes apply immediately — visit the{" "}
          <Link to="/" className="text-brand-700 hover:underline dark:text-brand-400">
            Dashboard
          </Link>{" "}
          to see them.
        </p>
        <button
          type="button"
          onClick={resetLayout}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Reset dashboard layout
        </button>
      </div>

      <ul className="flex flex-col gap-2">
        {cardOrder.map((id, index) => {
          const card = getDashboardCard(id);
          const hidden = hiddenCards.includes(id);
          return (
            <li
              key={id}
              className={`flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800 ${hidden ? "opacity-60" : ""}`}
            >
              <span className="text-sm text-slate-800 dark:text-slate-200">
                {card.label} {hidden && <span className="text-xs text-slate-500 dark:text-slate-400">(hidden)</span>}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    moveCardUp(id);
                  }}
                  disabled={index === 0}
                  aria-label={`Move ${card.label} up`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => {
                    moveCardDown(id);
                  }}
                  disabled={index === cardOrder.length - 1}
                  aria-label={`Move ${card.label} down`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => {
                    cycleCardSize(id);
                  }}
                  aria-label={`Change ${card.label} size (currently ${SIZE_LABEL[cardSizes[id]]})`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  {SIZE_LABEL[cardSizes[id]]}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    toggleCardVisibility(id);
                  }}
                  aria-label={hidden ? `Show ${card.label}` : `Hide ${card.label}`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  {hidden ? "Show" : "Hide"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
