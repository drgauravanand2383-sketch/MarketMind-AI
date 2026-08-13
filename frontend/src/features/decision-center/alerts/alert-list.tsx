import { useMemo, type ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { Pagination } from "@/components/table/pagination";
import { SkeletonList } from "@/components/states/skeleton";
import { SortableColumnHeader } from "@/components/table/sortable-column-header";
import { findRelatedRecommendation } from "@/features/decision-center/alerts/related-recommendation";
import { useAlertsList } from "@/hooks/use-alerts";
import { useAlertsUiStore, type AlertSortField } from "@/store/alerts-ui-store";
import type { RecommendationCandidate } from "@/types/portfolio";

const PRIORITY_OPTIONS = ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
const STATUS_OPTIONS = ["", "PENDING", "GENERATED", "SUPPRESSED", "DISMISSED", "EXPIRED"];

/**
 * `GET /alerts` supports server-side pagination + sort only — no filter
 * query params exist (confirmed against the real router: only
 * `page`/`page_size`/`sort`/`direction`). Priority/status filtering is
 * therefore client-side over whichever page is already fetched, not a
 * server-wide filter — a real limitation, not an oversight, documented
 * in `@/store/alerts-ui-store.ts`.
 */
export function AlertList({ relatedCandidates }: { relatedCandidates: RecommendationCandidate[] | undefined }): ReactNode {
  const sort = useAlertsUiStore((state) => state.sort);
  const direction = useAlertsUiStore((state) => state.direction);
  const page = useAlertsUiStore((state) => state.page);
  const pageSize = useAlertsUiStore((state) => state.pageSize);
  const priorityFilter = useAlertsUiStore((state) => state.priorityFilter);
  const statusFilter = useAlertsUiStore((state) => state.statusFilter);
  const setSort = useAlertsUiStore((state) => state.setSort);
  const setPage = useAlertsUiStore((state) => state.setPage);
  const setPriorityFilter = useAlertsUiStore((state) => state.setPriorityFilter);
  const setStatusFilter = useAlertsUiStore((state) => state.setStatusFilter);

  const alerts = useAlertsList({ page, page_size: pageSize, sort, direction });

  const filtered = useMemo(() => {
    return (alerts.data?.data ?? []).filter((alert) => {
      if (priorityFilter && alert.priority !== priorityFilter) return false;
      if (statusFilter && alert.status !== statusFilter) return false;
      return true;
    });
  }, [alerts.data?.data, priorityFilter, statusFilter]);

  function handleSort(field: AlertSortField): void {
    setSort(field);
  }

  if (alerts.isPending) return <SkeletonList rows={5} rowClassName="h-10 w-full" />;

  if (alerts.isError) {
    return (
      <ErrorState
        title="Couldn't load alerts"
        message={alerts.error.message}
        onRetry={() => {
          void alerts.refetch();
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="alert-priority-filter" className="sr-only">
          Filter by priority
        </label>
        <select
          id="alert-priority-filter"
          value={priorityFilter}
          onChange={(event) => {
            setPriorityFilter(event.target.value);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {PRIORITY_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option || "All priorities"}
            </option>
          ))}
        </select>
        <label htmlFor="alert-status-filter" className="sr-only">
          Filter by status
        </label>
        <select
          id="alert-status-filter"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option || "All statuses"}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No alerts match" description="Try clearing the priority or status filter, or evaluate more signals." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Alerts</caption>
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <SortableColumnHeader label="Ticker" field="ticker" activeField={sort} direction={direction} onSort={handleSort} />
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Reason
                </th>
                <SortableColumnHeader label="Priority" field="priority" activeField={sort} direction={direction} onSort={handleSort} />
                <SortableColumnHeader label="Status" field="status" activeField={sort} direction={direction} onSort={handleSort} />
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Confidence
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Related recommendation
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((alert) => {
                const related = findRelatedRecommendation(alert.ticker, relatedCandidates);
                return (
                  <tr key={alert.id} className="border-b border-slate-100 dark:border-slate-800/60">
                    <td className="px-3 py-2 font-medium text-slate-800 dark:text-slate-200">{alert.ticker}</td>
                    <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{alert.reason}</td>
                    <td className="px-3 py-2">
                      <PriorityBadge level={alert.priority} />
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{alert.status}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{alert.confidence.toFixed(0)}%</td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {related ? (
                        <span title="Inferred from a matching ticker — not a backend-asserted relationship">
                          {related.recommendation} (inferred)
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={alerts.data.page} pageSize={alerts.data.page_size} total={alerts.data.total} onPageChange={setPage} />
    </div>
  );
}
