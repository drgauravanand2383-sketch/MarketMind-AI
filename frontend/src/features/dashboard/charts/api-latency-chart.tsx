import type { ReactNode } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MOCK_API_LATENCY } from "@/features/dashboard/charts/api-latency-chart.mock";

export function ApiLatencyChart(): ReactNode {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">API response times</h3>
        <span className="text-xs text-slate-500 dark:text-slate-400">Demo data</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={MOCK_API_LATENCY} aria-label="API response times">
          <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
          <XAxis dataKey="time" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} unit="ms" />
          <Tooltip />
          <Line type="monotone" dataKey="latencyMs" stroke="#6366f1" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
