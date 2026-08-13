import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useExplainabilityResult } from "@/hooks/use-explainability";
import { useComparisonStore } from "@/store/comparison-store";
import type { ExplainabilityResult } from "@/types/explainability";

interface ComparisonRow {
  label: string;
  values: [string, string];
  differs: boolean;
}

function buildRows(a: ExplainabilityResult, b: ExplainabilityResult): ComparisonRow[] {
  const rows: [string, string, string][] = [
    ["Recommendation explanations", String(a.recommendation_explanations.length), String(b.recommendation_explanations.length)],
    ["Strategy explanations", String(a.strategy_explanations.length), String(b.strategy_explanations.length)],
    [
      "Overall risk score",
      a.risk_explanation ? a.risk_explanation.overall_risk_score.toFixed(0) : "—",
      b.risk_explanation ? b.risk_explanation.overall_risk_score.toFixed(0) : "—",
    ],
    [
      "Attribution portfolio return",
      a.performance_attribution ? `${a.performance_attribution.portfolio_return.toFixed(2)}%` : "—",
      b.performance_attribution ? `${b.performance_attribution.portfolio_return.toFixed(2)}%` : "—",
    ],
    ["Generated at", new Date(a.generated_at).toLocaleString(), new Date(b.generated_at).toLocaleString()],
    ["Overall summary", a.overall_summary, b.overall_summary],
  ];
  return rows.map(([label, valueA, valueB]) => ({ label, values: [valueA, valueB], differs: valueA !== valueB }));
}

/** Compares exactly the two explainability reports selected via
 * `useComparisonStore` (capped at 2) — presents already-fetched fields
 * side by side and flags where they differ; computes nothing new. */
export function ExplainabilityComparePage(): ReactNode {
  const compareIds = useComparisonStore((state) => state.explainabilityRequestIds);
  const clear = useComparisonStore((state) => state.clearExplainabilityResults);
  const [idA, idB] = compareIds;

  const resultA = useExplainabilityResult(idA ?? "");
  const resultB = useExplainabilityResult(idB ?? "");

  if (compareIds.length < 2) {
    return (
      <div className="p-6">
        <EmptyState
          icon="⚖️"
          title="Select two explainability reports to compare"
          description='Open an explanation and click "Add to comparison" — do this for two reports to see them here.'
        />
      </div>
    );
  }

  if (resultA.isPending || resultB.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (resultA.isError || resultB.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="One or both reports couldn't be loaded"
          message={(resultA.error ?? resultB.error)?.message ?? "Unknown error."}
          onRetry={() => {
            if (resultA.isError) void resultA.refetch();
            if (resultB.isError) void resultB.refetch();
          }}
        />
      </div>
    );
  }

  const rows = buildRows(resultA.data, resultB.data);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Compare explainability reports</h1>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Clear selection
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Explainability comparison</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Field
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/historical-analysis/explainability/$requestId" params={{ requestId: idA ?? "" }} className="hover:underline">
                  Report A
                </Link>
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/historical-analysis/explainability/$requestId" params={{ requestId: idB ?? "" }} className="hover:underline">
                  Report B
                </Link>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className={`border-b border-slate-100 dark:border-slate-800/60 ${row.differs ? "bg-amber-50 dark:bg-amber-500/10" : ""}`}>
                <td className="px-3 py-2 font-medium text-slate-700 dark:text-slate-300">{row.label}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[0]}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
