import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { DecisionHistoryList } from "@/features/decision-center/decision-history-list";
import { useWatchlistsList } from "@/hooks/use-watchlists";

/** `portfolio_id` *is* a `watchlist_id` (no separate `Portfolio` domain
 * model — established since Milestone 3) — the portfolio picker is just
 * the user's own watchlists. */
export function DecisionCenterLandingPage(): ReactNode {
  const watchlists = useWatchlistsList({ page: 1, page_size: 50, sort: "updated_at", direction: "desc" });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Decision Center</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Generate recommendations, evaluate strategy alignment, review risk, and check signals and alerts — for one portfolio at a
          time, in one workspace.
        </p>
      </div>

      <Panel title="Choose a portfolio">
        {watchlists.isPending && <SkeletonList rows={3} rowClassName="h-10 w-full" />}
        {watchlists.isError && (
          <ErrorState
            title="Couldn't load watchlists"
            message={watchlists.error.message}
            onRetry={() => {
              void watchlists.refetch();
            }}
          />
        )}
        {watchlists.isSuccess && watchlists.data.data.length === 0 && (
          <EmptyState title="No watchlists yet" description="Create a watchlist first — the Decision Center works from one portfolio at a time." />
        )}
        {watchlists.isSuccess && watchlists.data.data.length > 0 && (
          <ul className="flex flex-col gap-2">
            {watchlists.data.data.map((watchlist) => (
              <li key={watchlist.id} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{watchlist.name}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{watchlist.items.length} companies</p>
                </div>
                <Link
                  to="/decisions/$portfolioId"
                  params={{ portfolioId: watchlist.id }}
                  className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
                >
                  Open workspace
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Decision history (this session)">
        <DecisionHistoryList />
      </Panel>
    </div>
  );
}
