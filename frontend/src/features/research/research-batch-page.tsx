import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Badge } from "@/components/badge";
import { Panel } from "@/components/panel";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useRunBatchCompanyResearch } from "@/hooks/use-research";

const batchFormSchema = z.object({
  companies: z
    .array(z.object({ company_name: z.string().min(1, "Required"), ticker: z.string() }))
    .min(1, "Add at least one company"),
});

type BatchFormValues = z.infer<typeof batchFormSchema>;

export function ResearchBatchPage(): ReactNode {
  const runBatch = useRunBatchCompanyResearch();
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<BatchFormValues>({
    resolver: zodResolver(batchFormSchema),
    defaultValues: { companies: [{ company_name: "", ticker: "" }] },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "companies" });

  const submit = handleSubmit((values) => {
    runBatch.mutate({
      companies: values.companies.map((c) => ({
        company_name: c.company_name,
        ...(c.ticker && { ticker: c.ticker.toUpperCase() }),
      })),
    });
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Batch research</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">Research several companies in one run.</p>
      </div>

      <Panel title="Companies">
        <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4" noValidate aria-busy={runBatch.isPending}>
          <ul className="flex flex-col gap-3">
            {fields.map((field, index) => (
              <li key={field.id} className="flex items-end gap-3">
                <div className="flex-1">
                  <FormField
                    label={`Company ${String(index + 1)} name`}
                    autoComplete="off"
                    error={errors.companies?.[index]?.company_name?.message}
                    {...register(`companies.${String(index)}.company_name` as const)}
                  />
                </div>
                <div className="w-32">
                  <FormField label="Ticker (optional)" autoComplete="off" {...register(`companies.${String(index)}.ticker` as const)} />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    remove(index);
                  }}
                  disabled={fields.length <= 1}
                  aria-label={`Remove company ${String(index + 1)}`}
                  className="rounded-md px-2 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 dark:text-red-400 dark:hover:bg-red-950"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          {errors.companies?.root && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              {errors.companies.root.message}
            </p>
          )}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                append({ company_name: "", ticker: "" });
              }}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Add company
            </button>
            <LoadingButton isLoading={runBatch.isPending} loadingText="Researching…">
              Run batch research
            </LoadingButton>
            {runBatch.isPending && (
              <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
                Researching {fields.length} {fields.length === 1 ? "company" : "companies"}…
              </p>
            )}
          </div>
        </form>
      </Panel>

      {runBatch.isSuccess && (
        <Panel title="Results">
          <ul className="flex flex-col gap-2">
            {runBatch.data.map((envelope) => (
              <li
                key={envelope.request_id}
                className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800"
              >
                <Link
                  to="/research/$requestId"
                  params={{ requestId: envelope.request_id }}
                  className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                >
                  {envelope.report.company_overview.company_name}
                </Link>
                <Badge
                  label={envelope.report.company_overview.matched ? "Matched" : "Unmatched"}
                  tone={envelope.report.company_overview.matched ? "auto" : "neutral"}
                />
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {runBatch.isError && (
        <Panel title="Results">
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {runBatch.error.message}
          </p>
        </Panel>
      )}
    </div>
  );
}
