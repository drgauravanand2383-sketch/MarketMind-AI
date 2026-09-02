import { useMemo, type ReactNode } from "react";
import { DashboardCardFrame } from "@/features/dashboard/dashboard-card-frame";
import { DASHBOARD_CARDS, getDashboardCard } from "@/features/dashboard/dashboard-card-registry";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { useAuthStore } from "@/store/auth-store";

const NO_PERMISSIONS: string[] = [];

/**
 * Renders every registered card (`dashboard-card-registry.tsx`) in the
 * order/size `dashboard-layout-store.ts` records, skipping hidden ones —
 * a single unified `grid-cols-4` grid rather than the fixed, hand-laid-
 * out rows Milestones 2-7 used, so any card can be reordered/resized
 * relative to any other, not just within its original row.
 */
export function DashboardPage(): ReactNode {
  const cardOrder = useDashboardLayoutStore((state) => state.cardOrder);
  const hiddenCards = useDashboardLayoutStore((state) => state.hiddenCards);
  const isCustomizing = useDashboardLayoutStore((state) => state.isCustomizing);
  const toggleCustomizing = useDashboardLayoutStore((state) => state.toggleCustomizing);
  const toggleCardVisibility = useDashboardLayoutStore((state) => state.toggleCardVisibility);
  const resetLayout = useDashboardLayoutStore((state) => state.resetLayout);
  const permissions = useAuthStore((state) => state.user?.permissions ?? NO_PERMISSIONS);

  /** A card gated on a permission the current user lacks is dropped
   * everywhere — not rendered, and not offered in the customize "hidden
   * cards" list. Every other card is shown to every authenticated user,
   * exactly as before. */
  const permittedOrder = useMemo(
    () =>
      cardOrder.filter((id) => {
        const card = getDashboardCard(id);
        return !card.requiresPermission || permissions.includes(card.requiresPermission);
      }),
    [cardOrder, permissions],
  );

  const visibleOrder = permittedOrder.filter((id) => !hiddenCards.includes(id));
  const hiddenDefinitions = permittedOrder.filter((id) => hiddenCards.includes(id)).map((id) => getDashboardCard(id));

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Dashboard</h1>
        <div className="flex items-center gap-2">
          {isCustomizing && (
            <button
              type="button"
              onClick={resetLayout}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Reset layout
            </button>
          )}
          <button
            type="button"
            onClick={toggleCustomizing}
            aria-pressed={isCustomizing}
            className={
              isCustomizing
                ? "rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
                : "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            }
          >
            {isCustomizing ? "Done customizing" : "Customize dashboard"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        {visibleOrder.map((id, index) => (
          <DashboardCardFrame key={id} card={getDashboardCard(id)} isFirst={index === 0} isLast={index === visibleOrder.length - 1} />
        ))}
      </div>

      {isCustomizing && hiddenDefinitions.length > 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-4 dark:border-slate-700">
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Hidden cards</h2>
          <ul className="flex flex-wrap gap-2">
            {hiddenDefinitions.map((card) => (
              <li key={card.id}>
                <button
                  type="button"
                  onClick={() => {
                    toggleCardVisibility(card.id);
                  }}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Show {card.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {visibleOrder.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Every card is hidden. {DASHBOARD_CARDS.length > 0 && "Use “Customize dashboard” to bring one back."}
        </p>
      )}
    </div>
  );
}
