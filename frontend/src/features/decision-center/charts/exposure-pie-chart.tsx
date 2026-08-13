import type { ReactNode } from "react";
import { Legend, Pie, PieChart, ResponsiveContainer, Sector, Tooltip } from "recharts";
import type { PortfolioExposure } from "@/types/portfolio";

const PALETTE = ["#0ea5e9", "#8b5cf6", "#22c55e", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1", "#f97316"];

/** Renders a sector/country/industry exposure breakdown as a pie chart —
 * `dimension` selects which of `PortfolioExposure`'s three mutually
 * exclusive fields to read (only one is ever populated per entry). */
export function ExposurePieChart({
  exposures,
  dimension,
  label,
}: {
  exposures: PortfolioExposure[];
  dimension: "sector" | "country" | "industry";
  label: string;
}): ReactNode {
  const data = exposures.filter((e) => e[dimension] !== null).map((e) => ({ name: e[dimension] ?? "", value: e.weight }));
  const colorByName = new Map(data.map((entry, index) => [entry.name, PALETTE[index % PALETTE.length]]));

  if (data.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No {dimension} exposure data.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <PieChart aria-label={label}>
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
        <Tooltip formatter={(value: number) => `${(value * 100).toFixed(0)}%`} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
