import type { ReactNode } from "react";
import { Legend, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from "recharts";
import { EmptyState } from "@/components/states/empty-state";
import type { ContributionBreakdown } from "@/types/explainability";

const PALETTE = ["#0ea5e9", "#8b5cf6", "#22c55e", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1", "#f97316", "#a855f7", "#84cc16", "#06b6d4", "#f43f5e"];

/** Groups an already-computed `ContributionBreakdown[]` by category and
 * sums `contribution_percent` per category — a presentational grouping
 * of real values, never a recalculated contribution. */
export function ContributionDistributionChart({ items }: { items: ContributionBreakdown[] }): ReactNode {
  const totals = new Map<string, number>();
  for (const item of items) {
    totals.set(item.category, (totals.get(item.category) ?? 0) + item.contribution_percent);
  }
  const data = [...totals.entries()].map(([name, value]) => ({ name, value }));
  const colorByName = new Map(data.map((entry, index) => [entry.name, PALETTE[index % PALETTE.length]]));

  if (data.length === 0) {
    return <EmptyState title="No contribution data" description="No contribution breakdown was reported to chart." />;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <PieChart aria-label="Contribution distribution by category">
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius={40}
          outerRadius={80}
          paddingAngle={2}
          shape={(props) => {
            const { cx, cy, innerRadius, outerRadius, startAngle, endAngle } = props;
            const name = typeof props.name === "string" ? props.name : "";
            const fill = colorByName.get(name) ?? "#94a3b8";
            return (
              <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius} startAngle={startAngle} endAngle={endAngle} fill={fill} />
            );
          }}
        />
        <Tooltip formatter={(value: number) => `${value.toFixed(1)}%`} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
