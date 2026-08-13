import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog } from "@/components/dialog";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useAddCompany } from "@/hooks/use-watchlists";

const addCompanySchema = z.object({
  ticker: z.string().min(1, "Ticker is required"),
  company_name: z.string(),
  sector: z.string(),
  country: z.string(),
  theme: z.string(),
  notes: z.string(),
});

type AddCompanyValues = z.infer<typeof addCompanySchema>;

const DEFAULT_VALUES: AddCompanyValues = {
  ticker: "",
  company_name: "",
  sector: "",
  country: "",
  theme: "",
  notes: "",
};

export function AddCompanyDialog({
  watchlistId,
  open,
  onClose,
}: {
  watchlistId: string;
  open: boolean;
  onClose: () => void;
}): ReactNode {
  const addCompany = useAddCompany(watchlistId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AddCompanyValues>({ resolver: zodResolver(addCompanySchema), defaultValues: DEFAULT_VALUES });

  const onSubmit = handleSubmit((values) => {
    addCompany.mutate(
      {
        ticker: values.ticker,
        company_name: values.company_name || null,
        sector: values.sector || null,
        country: values.country || null,
        theme: values.theme || null,
        notes: values.notes || null,
      },
      {
        onSuccess: () => {
          reset(DEFAULT_VALUES);
          onClose();
        },
      },
    );
  });

  function handleClose(): void {
    reset(DEFAULT_VALUES);
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Add company">
      <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4" noValidate>
        <FormField label="Ticker" autoComplete="off" error={errors.ticker?.message} {...register("ticker")} />
        <FormField label="Company name (optional)" autoComplete="off" {...register("company_name")} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField label="Sector (optional)" autoComplete="off" {...register("sector")} />
          <FormField label="Country (optional)" autoComplete="off" {...register("country")} />
        </div>
        <FormField label="Theme (optional)" autoComplete="off" {...register("theme")} />
        <FormField label="Notes (optional)" autoComplete="off" {...register("notes")} />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <LoadingButton isLoading={addCompany.isPending} loadingText="Adding…">
            Add
          </LoadingButton>
        </div>
      </form>
    </Dialog>
  );
}
