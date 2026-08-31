import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { RankedAssetTable } from "@/features/global-markets/ranked-asset-table";
import { useCategoryReport, useRankedAssets } from "@/hooks/use-global-markets";
import type { ReportCategory } from "@/types/global-markets";

/** One report category's full content: its Top-N ranked-asset table plus
 * (when one was generated) the LLM-produced narrative summary/risk note.
 * Fetches independently of every other tab — same "each tab owns its own
 * data fetching" convention `DecisionWorkspacePage`'s per-tab panels
 * already establish, so switching tabs never blocks on an unrelated
 * category's request. */
export function CategoryPanel({ runId, category, title }: { runId: string; category: ReportCategory; title: string }): ReactNode {
  const rankedAssets = useRankedAssets(runId, category);
  const report = useCategoryReport(runId, category);

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
      {report.data && (
        <Panel>
          <p className="text-sm text-slate-700 dark:text-slate-300">{report.data.overall_summary}</p>
          {report.data.risk_note && <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">⚠ {report.data.risk_note}</p>}
        </Panel>
      )}

      {assets.length === 0 ? (
        <EmptyState title={`No ranked assets for ${title}`} description="This category didn't produce any ranked results in this run." />
      ) : (
        <RankedAssetTable assets={assets} />
      )}
    </div>
  );
}
