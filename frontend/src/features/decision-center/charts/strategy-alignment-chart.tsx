import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useShowDataLabels } from "@/features/decision-center/charts/chart-preferences";
import type { StrategyMatch } from "@/types/strategy";

export function StrategyAlignmentChart({ matches }: { matches: StrategyMatch[] }): ReactNode {
  const showDataLabels = useShowDataLabels();
  const data = [...matches].sort((a, b) => b.alignment_score - a.alignment_score).map((m) => ({
    name: m.strategy_name,
    alignment: m.alignment_score,
  }));

  if (data.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">No strategy matches to chart.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={224}>
      <BarChart data={data} aria-label="Strategy alignment">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="alignment" fill="#6366f1" radius={[4, 4, 0, 0]}>
          {showDataLabels && <LabelList dataKey="alignment" position="top" fontSize={11} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
