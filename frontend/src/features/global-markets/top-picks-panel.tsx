import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { CATEGORY_DISPLAY_NAMES } from "@/features/global-markets/category-labels";
import { formatRunTimestampIst } from "@/features/global-markets/run-timestamp";
import { useTopPicksAcrossCategories, type CategoryTopPicks } from "@/hooks/use-global-markets";
import { PENNY_MICROCAP_REPORT_CATEGORIES, type IntelligenceRun, type PerformanceWindow, type RankedAsset } from "@/types/global-markets";

/** How many ranks per category the "Top Picks" digest surfaces — the
 * run's own highest-conviction names, not its full Top-15/Top-20 list
 * (that stays on each category's own tab). */
const TOP_PICKS_DEPTH = 3;

const HEADLINE_WINDOWS: PerformanceWindow[] = ["1Y", "5Y"];
const PENNY_CATEGORIES = new Set<string>(PENNY_MICROCAP_REPORT_CATEGORIES);

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function returnToneClass(value: number): string {
  return value >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400";
}

function formatPrice(price: number | null, currency: string | null): string {
  if (price === null) return "—";
  const formatted = price.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return currency ? `${currency} ${formatted}` : formatted;
}

function ReturnValue({ asset, window }: { asset: RankedAsset; window: PerformanceWindow }): ReactNode {
  const entry = asset.performance_windows.find((candidate) => candidate.window === window);
  if (!entry) return <span className="text-slate-400 dark:text-slate-500">—</span>;
  if (!entry.is_complete) {
    return (
      <span className="text-slate-400 dark:text-slate-500" title="Partial: history does not fully cover this window">
        {formatPercent(entry.percent_change)}
        <span aria-hidden="true">*</span>
      </span>
    );
  }
  return <span className={returnToneClass(entry.percent_change)}>{formatPercent(entry.percent_change)}</span>;
}

function CategoryGroup({ group }: { group: CategoryTopPicks }): ReactNode {
  const label = CATEGORY_DISPLAY_NAMES[group.category];

  return (
    <section className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{label}</h3>
        {PENNY_CATEGORIES.has(group.category) && (
          <span className="text-xs text-amber-700 dark:text-amber-400">higher risk</span>
        )}
      </div>

      {group.isPending ? (
        <SkeletonList rows={TOP_PICKS_DEPTH} rowClassName="h-6 w-full" />
      ) : group.isError ? (
        <p className="text-xs text-red-700 dark:text-red-400">Couldn&apos;t load this category&apos;s picks.</p>
      ) : group.assets.length === 0 ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">No ranked assets in this run.</p>
      ) : (
        <ol className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800/60">
          {group.assets.map((asset) => (
            <li key={asset.snapshot.ticker} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-sm">
              <span className="w-5 shrink-0 text-xs font-medium text-slate-400 dark:text-slate-500">#{asset.rank}</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">{asset.snapshot.ticker}</span>
              {asset.snapshot.name && (
                <span className="min-w-0 flex-1 truncate text-xs text-slate-500 dark:text-slate-400">{asset.snapshot.name}</span>
              )}
              <span className="text-xs text-slate-600 dark:text-slate-300">
                {formatPrice(asset.snapshot.price, asset.snapshot.currency)}
              </span>
              {HEADLINE_WINDOWS.map((window) => (
                <span key={window} className="whitespace-nowrap text-xs tabular-nums">
                  <span className="text-slate-400 dark:text-slate-500">{window} </span>
                  <ReturnValue asset={asset} window={window} />
                </span>
              ))}
              <span className="text-xs text-slate-500 dark:text-slate-400">score {asset.final_score.toFixed(1)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/**
 * "Top Picks" — the run's rank-1..3 assets across all nine categories in
 * one place, so a user doesn't have to open every tab to see the day's
 * highest-conviction names. Purely a projection of the persisted,
 * already-ranked `RankedAsset` rows: no recalculation, no re-ranking, no
 * historical-data math in the browser (`useTopPicksAcrossCategories`).
 */
export function TopPicksPanel({ run }: { run: IntelligenceRun }): ReactNode {
  const picks = useTopPicksAcrossCategories(run.id, TOP_PICKS_DEPTH);
  const asOf = formatRunTimestampIst(run.completed_at);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          The top {TOP_PICKS_DEPTH} ranked assets in each of the nine categories for this run.
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {asOf ? `As of ${asOf}` : `Run date ${run.run_date}`}
        </p>
      </div>

      {picks.isError ? (
        <ErrorState
          title="Couldn't load Top Picks"
          message="None of the category rankings could be loaded for this run."
          onRetry={picks.refetch}
        />
      ) : picks.byCategory.every((group) => !group.isPending && group.assets.length === 0 && !group.isError) ? (
        <EmptyState
          icon="🌐"
          title="No ranked assets in this run"
          description="This run completed without producing ranked results in any category."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {picks.byCategory.map((group) => (
            <CategoryGroup key={group.category} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}
