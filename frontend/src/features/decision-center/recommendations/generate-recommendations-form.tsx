import type { ReactNode } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useGenerateRecommendations } from "@/hooks/use-portfolio";
import type { CandidateEvidence } from "@/types/portfolio";

const candidateSchema = z.object({
  ticker: z.string().min(1, "Required"),
  company_name: z.string(),
  sector: z.string(),
  country: z.string(),
  industry: z.string(),
});

const generateFormSchema = z.object({
  candidates: z.array(candidateSchema).min(1, "Add at least one candidate"),
});

type GenerateFormValues = z.infer<typeof generateFormSchema>;

function toCandidateEvidence(values: GenerateFormValues["candidates"][number]): CandidateEvidence {
  return {
    ticker: values.ticker.toUpperCase(),
    ...(values.company_name && { company_name: values.company_name }),
    ...(values.sector && { sector: values.sector }),
    ...(values.country && { country: values.country }),
    ...(values.industry && { industry: values.industry }),
  };
}

/** `react-hook-form`'s `FieldPath` needs a numeric-literal template
 * (`candidates.${number}.field`) to type-check, but the numeric
 * interpolation itself trips `@typescript-eslint/restrict-template-expressions`
 * — isolated here as the one intentional, reviewed exception rather than
 * disabling the rule at each call site. */
function candidateField<F extends "ticker" | "company_name" | "sector" | "country" | "industry">(
  index: number,
  field: F,
): `candidates.${number}.${F}` {
  // eslint-disable-next-line @typescript-eslint/restrict-template-expressions -- index is a number by construction (array index)
  return `candidates.${index}.${field}`;
}

/**
 * `POST /portfolio/recommendations` requires the caller to supply
 * `evidence: CandidateEvidence[]` directly — the engine never fetches
 * Screening/Signals/Alerts/Research itself. By explicit product
 * decision, this form only collects each candidate's plain identity
 * (ticker/company/sector/country/industry) — the same manual-entry
 * pattern Milestone 4 established for research/screening — not full
 * evidence attachment. The backend scores whatever it can from what's
 * given.
 */
export function GenerateRecommendationsForm({ portfolioId }: { portfolioId: string }): ReactNode {
  const generate = useGenerateRecommendations();
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<GenerateFormValues>({
    resolver: zodResolver(generateFormSchema),
    defaultValues: { candidates: [{ ticker: "", company_name: "", sector: "", country: "", industry: "" }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "candidates" });

  const submit = handleSubmit((values) => {
    generate.mutate({ portfolio_id: portfolioId, evidence: values.candidates.map(toCandidateEvidence) });
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4" noValidate aria-busy={generate.isPending}>
      <ul className="flex flex-col gap-3">
        {fields.map((field, index) => (
          <li key={field.id} className="flex flex-wrap items-end gap-2">
            <div className="w-24">
              <FormField
                label="Ticker"
                autoComplete="off"
                error={errors.candidates?.[index]?.ticker?.message}
                {...register(candidateField(index, "ticker"))}
              />
            </div>
            <div className="w-40">
              <FormField label="Company name" autoComplete="off" {...register(candidateField(index, "company_name"))} />
            </div>
            <div className="w-32">
              <FormField label="Sector" autoComplete="off" {...register(candidateField(index, "sector"))} />
            </div>
            <div className="w-24">
              <FormField label="Country" autoComplete="off" {...register(candidateField(index, "country"))} />
            </div>
            <div className="w-32">
              <FormField label="Industry" autoComplete="off" {...register(candidateField(index, "industry"))} />
            </div>
            <button
              type="button"
              onClick={() => {
                remove(index);
              }}
              disabled={fields.length <= 1}
              aria-label={`Remove candidate ${String(index + 1)}`}
              className="rounded-md px-2 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950"
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      {errors.candidates?.root && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          {errors.candidates.root.message}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            append({ ticker: "", company_name: "", sector: "", country: "", industry: "" });
          }}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Add candidate
        </button>
        <LoadingButton isLoading={generate.isPending} loadingText="Generating…">
          Generate recommendations
        </LoadingButton>
        {generate.isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Scoring {fields.length} {fields.length === 1 ? "candidate" : "candidates"}…
          </p>
        )}
      </div>
    </form>
  );
}
