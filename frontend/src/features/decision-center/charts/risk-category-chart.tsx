import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Rectangle, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useShowDataLabels } from "@/features/decision-center/charts/chart-preferences";
import type { RiskMetric, RiskSeverity } from "@/types/portfolio";

const SEVERITY_COLOR: Record<RiskSeverity, string> = {
  LOW: "#22c55e",
  MODERATE: "#f59e0b",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};
const FALLBACK_COLOR = "#94a3b8";

function isRiskSeverity(value: unknown): value is RiskSeverity {
  return value === "LOW" || value === "MODERATE" || value === "HIGH" || value === "CRITICAL";
}

function extractSeverity(payload: unknown): RiskSeverity | undefined {
  if (payload && typeof payload === "object" && "severity" in payload) {
    return isRiskSeverity(payload.severity) ? payload.severity : undefined;
  }
  return undefined;
}

export function RiskCategoryChart({ metrics }: { metrics: RiskMetric[] }): ReactNode {
  const showDataLabels = useShowDataLabels();
  const data = metrics.map((metric) => ({ category: metric.category, score: metric.score, severity: metric.severity }));

  if (data.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No risk metrics to chart.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <BarChart data={data} aria-label="Risk category breakdown">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="category" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar
          dataKey="score"
          radius={[4, 4, 0, 0]}
          shape={(props) => {
            const severity = extractSeverity(props.payload);
            const fill = severity ? SEVERITY_COLOR[severity] : FALLBACK_COLOR;
            return <Rectangle x={props.x} y={props.y} width={props.width} height={props.height} radius={4} fill={fill} />;
          }}
        >
          {showDataLabels && <LabelList dataKey="score" position="top" fontSize={11} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
