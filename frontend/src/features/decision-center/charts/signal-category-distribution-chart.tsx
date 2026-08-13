import type { ReactNode } from "react";
import { Legend, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from "recharts";
import type { SignalResult } from "@/types/signals";

const PALETTE = ["#0ea5e9", "#8b5cf6", "#22c55e", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1", "#f97316"];

/** Counts each already-returned `SignalResult` by its own `category` —
 * a presentation-only grouping, not a new metric. */
export function SignalCategoryDistributionChart({ results }: { results: SignalResult[] }): ReactNode {
  const counts = new Map<string, number>();
  for (const result of results) {
    counts.set(result.category, (counts.get(result.category) ?? 0) + 1);
  }
  const data = [...counts.entries()].map(([name, value]) => ({ name, value }));
  const colorByName = new Map(data.map((entry, index) => [entry.name, PALETTE[index % PALETTE.length]]));

  if (data.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No signal results to chart.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <PieChart aria-label="Signal category distribution">
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
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
