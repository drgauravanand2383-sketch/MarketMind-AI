import type { ReactNode } from "react";

export interface WeightedBarItem {
  label: string;
  weight: number;
}

function formatCount(weight: number): string {
  return String(weight);
}

function formatPercent(weight: number): string {
  return `${(weight * 100).toFixed(0)}%`;
}

/** A labeled list of proportional bars, scaled to the largest item's own
 * `weight` — used anywhere a domain has a derived, weighted breakdown
 * (research's evidence-mention sector/country exposure, risk's
 * portfolio sector/country/industry exposure) rather than a single
 * canonical value to show instead. `weight`'s own meaning is
 * domain-specific (a raw mention count for Company Research, a 0-1
 * fraction of portfolio holdings for Risk) — pass `valueFormat` to match:
 * `"count"` (default) shows the bare number, `"percent"` multiplies by
 * 100. */
export function WeightedBarList({
  title,
  items,
  emptyMessage,
  valueFormat = "count",
}: {
  title: string;
  items: WeightedBarItem[];
  emptyMessage: string;
  valueFormat?: "count" | "percent";
}): ReactNode {
  const format = valueFormat === "percent" ? formatPercent : formatCount;

  if (items.length === 0) {
    return (
      <div>
        {title && <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h3>}
        <p className="text-sm text-slate-500 dark:text-slate-400">{emptyMessage}</p>
      </div>
    );
  }

  const maxWeight = Math.max(...items.map((item) => item.weight), 1e-9);

  return (
    <div>
      {title && <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h3>}
      <ul className="flex flex-col gap-1.5">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-2 text-sm">
            <span className="w-28 shrink-0 truncate text-slate-700 dark:text-slate-300">{item.label}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <span
                className="block h-full rounded-full bg-brand-500"
                style={{ width: `${String(Math.max(4, (item.weight / maxWeight) * 100))}%` }}
              />
            </span>
            <span className="w-12 shrink-0 text-right text-xs text-slate-500 dark:text-slate-400">{format(item.weight)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
