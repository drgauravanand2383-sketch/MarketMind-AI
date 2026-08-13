import { useMemo, useState, type ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import { SIGNAL_CATEGORIES } from "@/types/signals";
import type { SignalResult } from "@/types/signals";

type CategoryFilter = "ALL" | (typeof SIGNAL_CATEGORIES)[number];
type SortField = "score" | "confidence" | "ticker";

/**
 * `SignalBatchResult` has no server-side grouping/sorting/filtering —
 * `SignalDetectionService` is synchronous and stateless, with no
 * persisted, filterable list across multiple evaluate runs. Grouping by
 * category, sorting, and filtering all happen client-side over whatever
 * single batch is currently loaded (the same reasoned exception
 * Milestone 4 established for screening results).
 */
export function SignalResultsList({ results }: { results: SignalResult[] }): ReactNode {
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("ALL");
  const [triggeredOnly, setTriggeredOnly] = useState(false);
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDesc, setSortDesc] = useState(true);

  const filtered = useMemo(() => {
    return results.filter((result) => {
      if (categoryFilter !== "ALL" && result.category !== categoryFilter) return false;
      if (triggeredOnly && !result.triggered) return false;
      return true;
    });
  }, [results, categoryFilter, triggeredOnly]);

  const grouped = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => {
      const comparison = sortField === "ticker" ? a.ticker.localeCompare(b.ticker) : a[sortField] - b[sortField];
      return sortDesc ? -comparison : comparison;
    });
    const byCategory = new Map<string, SignalResult[]>();
    for (const result of sorted) {
      const bucket = byCategory.get(result.category) ?? [];
      bucket.push(result);
      byCategory.set(result.category, bucket);
    }
    return byCategory;
  }, [filtered, sortField, sortDesc]);

  function toggleSort(field: SortField): void {
    if (field === sortField) setSortDesc((prev) => !prev);
    else {
      setSortField(field);
      setSortDesc(true);
    }
  }

  if (results.length === 0) {
    return <EmptyState title="No results yet" description="Evaluate a signal definition above to see results here." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="signal-category-filter" className="sr-only">
          Filter by category
        </label>
        <select
          id="signal-category-filter"
          value={categoryFilter}
          onChange={(event) => {
            setCategoryFilter(event.target.value as CategoryFilter);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          <option value="ALL">All categories</option>
          {SIGNAL_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-300">
          <input type="checkbox" checked={triggeredOnly} onChange={(event) => { setTriggeredOnly(event.target.checked); }} />
          Triggered only
        </label>
        <div className="ml-auto flex gap-1">
          {(["score", "confidence", "ticker"] as const).map((field) => (
            <button
              key={field}
              type="button"
              onClick={() => {
                toggleSort(field);
              }}
              aria-pressed={sortField === field}
              className={
                sortField === field
                  ? "rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white"
                  : "rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }
            >
              Sort by {field} {sortField === field ? (sortDesc ? "▼" : "▲") : ""}
            </button>
          ))}
        </div>
      </div>

      {grouped.size === 0 ? (
        <EmptyState title="No results match this filter" description="Try clearing the category filter or the triggered-only toggle." />
      ) : (
        [...grouped.entries()].map(([category, categoryResults]) => (
          <div key={category}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {category} ({categoryResults.length})
            </h3>
            <ul className="flex flex-col gap-2">
              {categoryResults.map((result) => (
                <li key={`${result.ticker}-${result.signal_name}`} className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-medium text-slate-900 dark:text-slate-100">{result.ticker}</span>
                      {result.company_name && <span className="ml-2 text-sm text-slate-500 dark:text-slate-400">{result.company_name}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      <PriorityBadge level={result.priority} />
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        score {result.score.toFixed(0)} · confidence {result.confidence.toFixed(0)}%
                      </span>
                      <span
                        className={
                          result.triggered
                            ? "rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/10 dark:text-green-400"
                            : "rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                        }
                      >
                        {result.triggered ? "Triggered" : "Not triggered"}
                      </span>
                    </div>
                  </div>
                  <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{result.reason}</p>
                  {(result.matched_conditions.length > 0 || result.failed_conditions.length > 0) && (
                    <details className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                      <summary className="cursor-pointer select-none">Triggered conditions</summary>
                      <ul className="mt-1 flex flex-col gap-0.5 pl-4">
                        {result.matched_conditions.map((condition) => (
                          <li key={condition.condition_id} className="text-green-700 dark:text-green-400">
                            ✓ {condition.field} {condition.operator}
                          </li>
                        ))}
                        {result.failed_conditions.map((condition) => (
                          <li key={condition.condition_id} className="text-red-700 dark:text-red-400">
                            ✕ {condition.field} {condition.operator} — {condition.reason ?? "did not pass"}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
