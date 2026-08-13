import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import type { CompanyResearchNarrative } from "@/types/research";

/** `narrative === null` means no LLM call was made at all (the company
 * was never matched to a known entity, so there was no evidence to
 * ground a narrative in) — an expected state, rendered here as an empty
 * state, never as an error. */
export function ResearchNarrativePanel({ narrative }: { narrative: CompanyResearchNarrative | null }): ReactNode {
  if (!narrative) {
    return (
      <EmptyState
        icon="🧭"
        title="No narrative available"
        description="This company wasn't matched to a known entity, so no evidence-grounded narrative was generated."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-700 dark:text-slate-300">{narrative.summary}</p>
      {narrative.key_findings.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Key findings
          </h3>
          <ul className="list-inside list-disc text-sm text-slate-700 dark:text-slate-300">
            {narrative.key_findings.map((finding, index) => (
              <li key={index}>{finding}</li>
            ))}
          </ul>
        </div>
      )}
      {narrative.risk_commentary && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Risk commentary
          </h3>
          <p className="text-sm text-slate-700 dark:text-slate-300">{narrative.risk_commentary}</p>
        </div>
      )}
    </div>
  );
}
