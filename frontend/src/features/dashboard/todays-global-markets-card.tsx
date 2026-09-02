import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { CATEGORY_DISPLAY_NAMES } from "@/features/global-markets/category-labels";
import { daysSinceRunDate, formatRunTimestampIst } from "@/features/global-markets/run-timestamp";
import { useLatestRun, useTopPicksAcrossCategories } from "@/hooks/use-global-markets";
import { ApiError } from "@/services/api/errors";
import type { IntelligenceRun, IntelligenceRunStatus } from "@/types/global-markets";

/** A run older than this many days is flagged stale on the card — the
 * daily workflow fires every morning, so a two-day-old "latest" run
 * means something has stopped. */
const STALE_AFTER_DAYS = 2;

/** How many names per segment the dashboard preview shows — just enough
 * to signal the day's leaders; the full list is one click away. */
const PREVIEW_DEPTH = 3;

const STATUS_BADGE_CLASS: Record<IntelligenceRunStatus, string> = {
  COMPLETED: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  PARTIAL: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  RUNNING: "bg-blue-100 text-blue-800 dark:bg-blue-500/10 dark:text-blue-400",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

function ViewFullReportLink(): ReactNode {
  return (
    <Link
      to="/global-markets"
      className="text-sm font-medium text-brand-700 hover:underline dark:text-brand-400"
    >
      View full report →
    </Link>
  );
}

function Preview({ run }: { run: IntelligenceRun }): ReactNode {
  const picks = useTopPicksAcrossCategories(run.id, PREVIEW_DEPTH);

  if (picks.isPending) {
    return <SkeletonList rows={5} rowClassName="h-5 w-full" />;
  }
  if (picks.isError) {
    return <p className="text-xs text-red-700 dark:text-red-400">Couldn&apos;t load this run&apos;s ranked assets.</p>;
  }

  const withAssets = picks.byCategory.filter((group) => group.assets.length > 0);
  if (withAssets.length === 0) {
    return (
      <p className="text-xs text-slate-500 dark:text-slate-400">
        This run completed without producing ranked results in any category.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-1">
      {withAssets.map((group) => (
        <li key={group.category} className="flex flex-wrap items-baseline gap-x-2 text-xs">
          <span className="font-medium text-slate-600 dark:text-slate-300">{CATEGORY_DISPLAY_NAMES[group.category]}:</span>
          <span className="text-slate-700 dark:text-slate-200">
            {group.assets.map((asset) => asset.snapshot.ticker).join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * "Today's Global Markets" dashboard card — surfaces the latest completed
 * Global Market Intelligence run (run date, status, IST completion time,
 * a top-3 preview per segment) so the feature is visible from the
 * dashboard, not only from its own page. Every value is read straight
 * from the persisted run — nothing is recalculated here. Gated on
 * `global_markets:read` by the dashboard registry, same permission the
 * page and API require.
 */
export function TodaysGlobalMarketsCard(): ReactNode {
  const latestRun = useLatestRun();

  if (latestRun.isPending) {
    return <SkeletonList rows={4} rowClassName="h-6 w-full" />;
  }

  if (latestRun.isError) {
    const isNotFound = latestRun.error instanceof ApiError && latestRun.error.status === 404;
    if (isNotFound) {
      return (
        <EmptyState
          icon="🌐"
          title="No intelligence run yet"
          description="The daily Global Market Intelligence run hasn't completed yet. Check back after the next scheduled run (08:30 IST)."
          action={<ViewFullReportLink />}
        />
      );
    }
    return (
      <ErrorState
        title="Couldn't load Global Markets"
        message={latestRun.error.message}
        onRetry={() => {
          void latestRun.refetch();
        }}
      />
    );
  }

  const run = latestRun.data;
  const completedAtIst = formatRunTimestampIst(run.completed_at);
  const staleDays = daysSinceRunDate(run.run_date);
  const isStale = staleDays >= STALE_AFTER_DAYS;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASS[run.status]}`}>
          {run.status}
        </span>
        <span className="text-sm text-slate-600 dark:text-slate-300">Run date {run.run_date}</span>
        {completedAtIst && <span className="text-xs text-slate-500 dark:text-slate-400">generated {completedAtIst}</span>}
      </div>

      {isStale && (
        <p
          role="status"
          className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300"
        >
          Last run was {staleDays} days ago — the daily run may have stopped.
        </p>
      )}

      <Preview run={run} />

      <div className="pt-1">
        <ViewFullReportLink />
      </div>
    </div>
  );
}
