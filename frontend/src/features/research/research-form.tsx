import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import type { CompanyResearchRequest } from "@/types/research";

const researchFormSchema = z.object({
  company_name: z.string().min(1, "Company name is required"),
  ticker: z.string(),
});

type ResearchFormValues = z.infer<typeof researchFormSchema>;

export interface ResearchFormProps {
  isPending: boolean;
  onSubmit: (body: CompanyResearchRequest) => void;
}

/** There is no backend company search/autocomplete endpoint (confirmed
 * against the real API surface for Milestone 4) — company entry is
 * plain free text, exactly like `company_name`/`ticker` on
 * `CompanyResearchRequest` itself. */
export function ResearchForm({ isPending, onSubmit }: ResearchFormProps): ReactNode {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResearchFormValues>({
    resolver: zodResolver(researchFormSchema),
    defaultValues: { company_name: "", ticker: "" },
  });

  const submit = handleSubmit((values) => {
    onSubmit({
      company_name: values.company_name,
      ...(values.ticker && { ticker: values.ticker.toUpperCase() }),
    });
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4" noValidate aria-busy={isPending}>
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="flex-1">
          <FormField
            label="Company name"
            placeholder="e.g. Apple Inc."
            autoComplete="off"
            error={errors.company_name?.message}
            {...register("company_name")}
          />
        </div>
        <div className="sm:w-40">
          <FormField
            label="Ticker (optional)"
            placeholder="e.g. AAPL"
            autoComplete="off"
            error={errors.ticker?.message}
            {...register("ticker")}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <LoadingButton isLoading={isPending} loadingText="Researching…">
          Run research
        </LoadingButton>
        {isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Researching — this can take a moment.
          </p>
        )}
      </div>
    </form>
  );
}
