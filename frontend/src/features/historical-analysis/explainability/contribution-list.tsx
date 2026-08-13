import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import type { ContributionBreakdown } from "@/types/explainability";

/** `ContributionBreakdown` is reused across five different places in the
 * explainability domain (per-candidate, per-strategy, per-attribution) —
 * one shared list component avoids duplicating the same row markup five
 * times. */
export function ContributionList({ items, emptyMessage }: { items: ContributionBreakdown[]; emptyMessage: string }): ReactNode {
  if (items.length === 0) {
    return <EmptyState title="Nothing here" description={emptyMessage} />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, index) => (
        <li key={`${item.source}-${String(index)}`} className="rounded-md border border-slate-200 p-2 text-sm dark:border-slate-800">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-slate-800 dark:text-slate-200">{item.source}</span>
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {item.category} · weight {item.weight.toFixed(2)} · {item.contribution_percent.toFixed(1)}%
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.description}</p>
        </li>
      ))}
    </ul>
  );
}
