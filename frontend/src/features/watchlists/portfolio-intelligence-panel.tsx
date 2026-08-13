import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { usePortfolioIntelligence } from "@/hooks/use-portfolio";
import { ApiError } from "@/services/api/errors";

export function PortfolioIntelligencePanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const intelligence = usePortfolioIntelligence(portfolioId);

  if (intelligence.isPending) return <SkeletonList rows={4} rowClassName="h-6 w-full" />;

  if (intelligence.isError) {
    const isServiceUnavailable = intelligence.error instanceof ApiError && intelligence.error.status === 503;
    if (isServiceUnavailable) {
      return (
        <EmptyState
          title="Portfolio intelligence unavailable"
          description="This backend deployment doesn't have the intelligence service configured."
        />
      );
    }
    return (
      <ErrorState
        title="Couldn't load portfolio intelligence"
        message={intelligence.error.message}
        onRetry={() => {
          void intelligence.refetch();
        }}
      />
    );
  }

  const data = intelligence.data;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-slate-700 dark:text-slate-300">{data.executive_summary}</p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Holdings</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{data.portfolio_overview.holding_count}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Matched holdings</p>
          <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            {data.portfolio_overview.matched_holding_count}
          </p>
        </div>
      </div>

      {data.concentration_observations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Concentration observations</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
            {data.concentration_observations.map((observation) => (
              <li key={observation}>{observation}</li>
            ))}
          </ul>
        </div>
      )}

      {data.relationship_observations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Relationship observations</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
            {data.relationship_observations.map((observation) => (
              <li key={observation}>{observation}</li>
            ))}
          </ul>
        </div>
      )}

      {data.notable_market_events.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Notable market events</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-600 dark:text-slate-300">
            {data.notable_market_events.map((event) => (
              <li key={event}>{event}</li>
            ))}
          </ul>
        </div>
      )}

      {data.data_quality_notes.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400">Data quality notes</h3>
          <ul className="mt-1 flex flex-col gap-1 text-sm text-slate-600 dark:text-slate-300">
            {data.data_quality_notes.map((note) => (
              <li key={note.code}>{note.description}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
