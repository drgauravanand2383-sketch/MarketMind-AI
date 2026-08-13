import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/states/empty-state";
import { useShowDataLabels } from "@/features/historical-analysis/charts/chart-preferences";
import type { ContributionBreakdown } from "@/types/explainability";

/** A bar per already-filtered `ContributionBreakdown` entry (e.g. every
 * `SECTOR`- or `COUNTRY`-category item) — used for both sector and
 * country attribution, since both are the same shape once filtered by
 * category (`features/historical-analysis/attribution/performance-
 * attribution-panel.tsx` does the filtering). */
export function AttributionBarChart({ items, label, color }: { items: ContributionBreakdown[]; label: string; color: string }): ReactNode {
  const showDataLabels = useShowDataLabels();

  if (items.length === 0) {
    return <EmptyState title={`No ${label.toLowerCase()} data`} description={`No ${label.toLowerCase()} was reported to chart.`} />;
  }

  const data = items.map((item) => ({ name: item.source, value: item.contribution_percent }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} aria-label={label} layout="vertical">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis type="number" tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={90} />
        <Tooltip formatter={(value) => `${Number(value).toFixed(1)}%`} />
        <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]}>
          {showDataLabels && <LabelList dataKey="value" position="right" fontSize={11} formatter={(v) => `${Number(v).toFixed(1)}%`} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
