import type { ReactNode } from "react";
import { PriorityBadge } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import type { RiskMetric } from "@/types/portfolio";

export function RiskMetricsTable({ metrics }: { metrics: RiskMetric[] }): ReactNode {
  if (metrics.length === 0) {
    return <EmptyState title="No risk metrics reported" description="The risk engine didn't emit any metrics for this portfolio." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Risk metrics</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Metric
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Category
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Score
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Severity
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Description
            </th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.metric_name} className="border-b border-slate-100 dark:border-slate-800/60">
              <td className="px-3 py-2 font-medium text-slate-800 dark:text-slate-200">{metric.metric_name}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{metric.category}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{metric.score.toFixed(0)}</td>
              <td className="px-3 py-2">
                <PriorityBadge level={metric.severity} />
              </td>
              <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">{metric.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
