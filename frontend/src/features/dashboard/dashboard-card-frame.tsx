import type { ReactNode } from "react";
import { ErrorBoundary } from "@/components/error-boundary";
import { ErrorState } from "@/components/states/error-state";
import type { DashboardCardDefinition } from "@/features/dashboard/dashboard-card-registry";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import type { CardSize } from "@/types/preferences";

const SIZE_COL_SPAN: Record<CardSize, string> = {
  sm: "lg:col-span-1",
  md: "lg:col-span-2",
  lg: "lg:col-span-4",
};

const SIZE_LABEL: Record<CardSize, string> = { sm: "Small", md: "Medium", lg: "Large" };

const CONTROL_BUTTON_CLASS =
  "rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800";

/** Wraps one registered dashboard card in its `Panel`-style frame, plus
 * (only while `isCustomizing`) Move up/down, Hide, and a size-cycle
 * button — the whole reorder/resize/hide mechanism, built entirely from
 * plain buttons rather than drag-and-drop (approved product decision,
 * `docs/frontend/MILESTONE_8.md`: no new dependency, fully keyboard-
 * accessible by default). `card.render()` is also wrapped in its own
 * `ErrorBoundary` (Milestone 9 audit fix) — previously the single
 * top-level boundary in `AppShell` meant one broken card took down the
 * entire dashboard page instead of just that card. */
export function DashboardCardFrame({ card, isFirst, isLast }: { card: DashboardCardDefinition; isFirst: boolean; isLast: boolean }): ReactNode {
  const isCustomizing = useDashboardLayoutStore((state) => state.isCustomizing);
  const size = useDashboardLayoutStore((state) => state.cardSizes[card.id]);
  const moveCardUp = useDashboardLayoutStore((state) => state.moveCardUp);
  const moveCardDown = useDashboardLayoutStore((state) => state.moveCardDown);
  const toggleCardVisibility = useDashboardLayoutStore((state) => state.toggleCardVisibility);
  const cycleCardSize = useDashboardLayoutStore((state) => state.cycleCardSize);

  return (
    <div className={SIZE_COL_SPAN[size]}>
      <section className="flex h-full flex-col rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        {(card.panelTitle ?? isCustomizing) && (
          <div className="mb-3 flex items-center justify-between gap-2">
            {card.panelTitle && <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{card.panelTitle}</h2>}
            {isCustomizing && (
              <div className="flex flex-wrap items-center gap-1" aria-label={`Customize ${card.label}`}>
                <button
                  type="button"
                  onClick={() => {
                    moveCardUp(card.id);
                  }}
                  disabled={isFirst}
                  aria-label={`Move ${card.label} up`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => {
                    moveCardDown(card.id);
                  }}
                  disabled={isLast}
                  aria-label={`Move ${card.label} down`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => {
                    cycleCardSize(card.id);
                  }}
                  aria-label={`Change ${card.label} size (currently ${SIZE_LABEL[size]})`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  {SIZE_LABEL[size]}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    toggleCardVisibility(card.id);
                  }}
                  aria-label={`Hide ${card.label}`}
                  className={CONTROL_BUTTON_CLASS}
                >
                  Hide
                </button>
              </div>
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <ErrorBoundary
            fallback={(error, reset) => (
              <ErrorState title={`${card.label} failed to load`} message={error.message} onRetry={reset} />
            )}
          >
            {card.render()}
          </ErrorBoundary>
        </div>
      </section>
    </div>
  );
}
