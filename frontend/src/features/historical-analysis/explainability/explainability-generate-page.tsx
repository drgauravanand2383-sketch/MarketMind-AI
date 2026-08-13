import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { GenerateExplanationForm } from "@/features/historical-analysis/explainability/generate-explanation-form";

export function ExplainabilityGeneratePage(): ReactNode {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Explainability</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Understand why a recommendation, strategy alignment, or risk assessment came out the way it did — every field
          shown is copied or derived from already-computed results, never recalculated.
        </p>
      </div>

      <Panel title="Generate an explanation">
        <GenerateExplanationForm />
      </Panel>
    </div>
  );
}
