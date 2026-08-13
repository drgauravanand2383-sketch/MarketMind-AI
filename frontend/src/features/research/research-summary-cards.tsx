import type { ReactNode } from "react";
import type { CompanyResearchReport } from "@/types/research";

function SummaryCard({ label, value, hint }: { label: string; value: string; hint?: string }): ReactNode {
  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

/** Confidence lives under `confidence_summary.overall_confidence` (a 0-1
 * float) — there is deliberately no separate top-level confidence field
 * on the report to read instead. */
export function ResearchSummaryCards({ report }: { report: CompanyResearchReport }): ReactNode {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <SummaryCard
        label="Confidence"
        value={`${(report.confidence_summary.overall_confidence * 100).toFixed(0)}%`}
        hint={report.confidence_summary.basis}
      />
      <SummaryCard label="Mentions" value={String(report.company_overview.mention_count)} hint="Evidence mention count" />
      <SummaryCard
        label="Supporting records"
        value={String(report.confidence_summary.supporting_record_count)}
      />
      <SummaryCard label="Match status" value={report.company_overview.matched ? "Matched" : "Unmatched"} />
    </div>
  );
}
