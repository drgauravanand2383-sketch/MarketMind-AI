import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { WeightedBarList } from "@/components/weighted-bar-list";
import { useResearchReport } from "@/hooks/use-research";
import { useComparisonStore } from "@/store/comparison-store";
import type { CompanyResearchReportEnvelope } from "@/types/research";

interface ComparisonRow {
  label: string;
  values: [string, string];
  differs: boolean;
}

function buildRows(a: CompanyResearchReportEnvelope, b: CompanyResearchReportEnvelope): ComparisonRow[] {
  const rows: [string, string, string][] = [
    ["Company", a.report.company_overview.company_name, b.report.company_overview.company_name],
    ["Ticker", a.report.company_overview.ticker ?? "—", b.report.company_overview.ticker ?? "—"],
    ["Match status", a.report.company_overview.matched ? "Matched" : "Unmatched", b.report.company_overview.matched ? "Matched" : "Unmatched"],
    [
      "Confidence",
      `${(a.report.confidence_summary.overall_confidence * 100).toFixed(0)}%`,
      `${(b.report.confidence_summary.overall_confidence * 100).toFixed(0)}%`,
    ],
    ["Mentions", String(a.report.company_overview.mention_count), String(b.report.company_overview.mention_count)],
    [
      "Supporting records",
      String(a.report.confidence_summary.supporting_record_count),
      String(b.report.confidence_summary.supporting_record_count),
    ],
    ["Top sector", a.report.sector_analysis[0]?.sector ?? "—", b.report.sector_analysis[0]?.sector ?? "—"],
    ["Top country", a.report.country_exposure[0]?.country ?? "—", b.report.country_exposure[0]?.country ?? "—"],
    ["Generated at", new Date(a.report.generated_at).toLocaleString(), new Date(b.report.generated_at).toLocaleString()],
  ];
  return rows.map(([label, valueA, valueB]) => ({ label, values: [valueA, valueB], differs: valueA !== valueB }));
}

/** Compares exactly the two reports selected via `useComparisonStore`
 * (capped at 2 by the store itself) — presents already-fetched fields
 * side by side and flags where they differ; computes nothing new. */
export function ResearchComparePage(): ReactNode {
  const compareIds = useComparisonStore((state) => state.researchRequestIds);
  const clear = useComparisonStore((state) => state.clearResearch);
  const [idA, idB] = compareIds;

  const reportA = useResearchReport(idA ?? "");
  const reportB = useResearchReport(idB ?? "");

  if (compareIds.length < 2) {
    return (
      <div className="p-6">
        <EmptyState
          icon="⚖️"
          title="Select two reports to compare"
          description='Open a research report and click "Add to comparison" — do this for two reports to see them here.'
        />
      </div>
    );
  }

  if (reportA.isPending || reportB.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (reportA.isError || reportB.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="One or both reports couldn't be loaded"
          message={
            (reportA.error ?? reportB.error)?.message ??
            "Reports aren't stored durably — if this isn't a transient error, run the research again and re-select it for comparison."
          }
          onRetry={() => {
            if (reportA.isError) void reportA.refetch();
            if (reportB.isError) void reportB.refetch();
          }}
        />
      </div>
    );
  }

  const rows = buildRows(reportA.data, reportB.data);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Compare research reports</h1>
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
          <caption className="sr-only">Research report comparison</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Field
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/research/$requestId" params={{ requestId: idA ?? "" }} className="hover:underline">
                  {reportA.data.report.company_overview.company_name}
                </Link>
              </th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                <Link to="/research/$requestId" params={{ requestId: idB ?? "" }} className="hover:underline">
                  {reportB.data.report.company_overview.company_name}
                </Link>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.label}
                className={`border-b border-slate-100 dark:border-slate-800/60 ${row.differs ? "bg-amber-50 dark:bg-amber-500/10" : ""}`}
              >
                <td className="px-3 py-2 font-medium text-slate-700 dark:text-slate-300">{row.label}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[0]}</td>
                <td className="px-3 py-2 text-slate-800 dark:text-slate-200">{row.values[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <WeightedBarList
          title="Sector exposure — A"
          items={reportA.data.report.sector_analysis.map((s) => ({ label: s.sector, weight: s.weight }))}
          emptyMessage="No sector exposure data."
        />
        <WeightedBarList
          title="Sector exposure — B"
          items={reportB.data.report.sector_analysis.map((s) => ({ label: s.sector, weight: s.weight }))}
          emptyMessage="No sector exposure data."
        />
      </div>
    </div>
  );
}
