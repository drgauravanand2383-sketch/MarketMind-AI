import { useMemo, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { DataFreshnessBadge } from "@/features/global-markets/data-freshness-badge";
import { RankedAssetTable } from "@/features/global-markets/ranked-asset-table";
import { useCategoryReport, useRankedAssets } from "@/hooks/use-global-markets";
import type { CategoryRunOutcome, ReportCategory } from "@/types/global-markets";

/** One report category's full content: its Top-N ranked-asset table plus
 * (when one was generated) the LLM-produced narrative summary/risk note
 * and per-asset commentary. Fetches independently of every other tab —
 * same "each tab owns its own data fetching" convention
 * `DecisionWorkspacePage`'s per-tab panels already establish, so
 * switching tabs never blocks on an unrelated category's request. */
export function CategoryPanel({
  runId,
  category,
  title,
  outcome,
}: {
  runId: string;
  category: ReportCategory;
  title: string;
  /** This category's own outcome from the parent `IntelligenceRun` —
   * carries the real freshness/failure detail this panel surfaces.
   * `undefined` only if the run somehow has no entry for this category
   * (never expected in practice, but not fatal — the panel still renders
   * without a freshness badge or a specific failure reason). */
  outcome: CategoryRunOutcome | undefined;
}): ReactNode {
  const rankedAssets = useRankedAssets(runId, category);
  const report = useCategoryReport(runId, category);

  const commentaryByTicker = useMemo(() => {
    if (!report.data) return undefined;
    return new Map(report.data.asset_commentaries.map((commentary) => [commentary.ticker, commentary.commentary]));
  }, [report.data]);

  if (rankedAssets.isPending) {
    return <SkeletonList rows={6} rowClassName="h-10 w-full" />;
  }

  if (rankedAssets.isError) {
    return (
      <ErrorState
        title={`Couldn't load ${title}`}
        message={rankedAssets.error.message}
        onRetry={() => {
          void rankedAssets.refetch();
        }}
      />
    );
  }

  const assets = rankedAssets.data.data;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <DataFreshnessBadge context={outcome?.market_session_context} />
      </div>

      {outcome?.succeeded === false && (
        <ErrorState
          title={`${title} failed to generate in this run`}
          message={outcome.error ?? "No further detail was recorded for this failure."}
        />
      )}

      {report.data && (
        <Panel>
          <p className="text-sm text-slate-700 dark:text-slate-300">{report.data.overall_summary}</p>
          {report.data.risk_note && <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">⚠ {report.data.risk_note}</p>}
        </Panel>
      )}

      {assets.length === 0 ? (
        outcome?.succeeded !== false && (
          <EmptyState title={`No ranked assets for ${title}`} description="This category didn't produce any ranked results in this run." />
        )
      ) : (
        <RankedAssetTable assets={assets} commentaryByTicker={commentaryByTicker} />
      )}
    </div>
  );
}
