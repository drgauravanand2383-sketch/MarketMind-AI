import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Rectangle, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useShowDataLabels } from "@/features/historical-analysis/charts/chart-preferences";
import type { BacktestResult } from "@/types/backtesting";

function extractValue(payload: unknown): number | undefined {
  if (payload && typeof payload === "object" && "value" in payload && typeof payload.value === "number") {
    return payload.value;
  }
  return undefined;
}

/** `portfolio_return`/`benchmark_return`/`excess_return` are copied
 * directly from `BacktestResult` — the same percentage numbers shown in
 * the summary cards, just charted for at-a-glance comparison. */
export function PortfolioVsBenchmarkChart({ result }: { result: BacktestResult }): ReactNode {
  const showDataLabels = useShowDataLabels();
  const data = [
    { name: "Portfolio", value: result.portfolio_return },
    { name: "Benchmark", value: result.benchmark_return },
    { name: "Excess", value: result.excess_return },
  ];

  return (
    <ResponsiveContainer width="100%" height={224}>
      <BarChart data={data} aria-label="Portfolio vs benchmark return">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
        <Bar
          dataKey="value"
          radius={[4, 4, 0, 0]}
          shape={(props) => {
            const value = extractValue(props.payload);
            const fill = value !== undefined && value >= 0 ? "#22c55e" : "#ef4444";
            return <Rectangle x={props.x} y={props.y} width={props.width} height={props.height} radius={4} fill={fill} />;
          }}
        >
          {showDataLabels && <LabelList dataKey="value" position="top" fontSize={11} formatter={(v) => `${Number(v).toFixed(1)}%`} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
