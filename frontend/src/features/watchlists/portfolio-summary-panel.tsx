import type { ReactNode } from "react";
import { Badge } from "@/components/badge";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { usePortfolioSummary } from "@/hooks/use-portfolio";

function DistributionList({ title, distribution }: { title: string; distribution: Record<string, number> }): ReactNode {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">{title}</h3>
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {entries.map(([label, count]) => (
          <li key={label} className="flex items-center gap-1">
            <Badge label={label} />
            <span className="text-xs text-slate-500 dark:text-slate-400">×{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PortfolioSummaryPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const summary = usePortfolioSummary(portfolioId);

  if (summary.isPending) return <SkeletonList rows={3} rowClassName="h-8 w-full" />;
  if (summary.isError) {
    return (
      <ErrorState
        title="Couldn't load portfolio summary"
        message={summary.error.message}
        onRetry={() => {
          void summary.refetch();
        }}
      />
    );
  }

  const data = summary.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Companies</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{data.total_companies}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Average confidence</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            {data.average_confidence === null ? "—" : `${(data.average_confidence * 100).toFixed(0)}%`}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Top sectors</p>
          <p className="text-sm text-slate-700 dark:text-slate-300">
            {data.top_sectors.length > 0 ? data.top_sectors.join(", ") : "—"}
          </p>
        </div>
      </div>
      <DistributionList title="Sector distribution" distribution={data.sector_distribution} />
      <DistributionList title="Country distribution" distribution={data.country_distribution} />
      <DistributionList title="Theme distribution" distribution={data.theme_distribution} />
    </div>
  );
}
