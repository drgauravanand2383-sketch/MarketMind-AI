import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog } from "@/components/dialog";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useCreateWatchlist } from "@/hooks/use-watchlists";

const createWatchlistSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string(),
});

type CreateWatchlistValues = z.infer<typeof createWatchlistSchema>;

export function CreateWatchlistDialog({ open, onClose }: { open: boolean; onClose: () => void }): ReactNode {
  const createWatchlist = useCreateWatchlist();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateWatchlistValues>({ resolver: zodResolver(createWatchlistSchema), defaultValues: { name: "", description: "" } });

  const onSubmit = handleSubmit((values) => {
    createWatchlist.mutate(values, {
      onSuccess: () => {
        reset();
        onClose();
      },
    });
  });

  function handleClose(): void {
    reset();
    onClose();
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Create watchlist">
      <form
        onSubmit={(event) => void onSubmit(event)}
        className="flex flex-col gap-4"
        noValidate
      >
        <FormField label="Name" autoComplete="off" error={errors.name?.message} {...register("name")} />
        <FormField label="Description (optional)" autoComplete="off" error={errors.description?.message} {...register("description")} />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <LoadingButton isLoading={createWatchlist.isPending} loadingText="Creating…">
            Create
          </LoadingButton>
        </div>
      </form>
    </Dialog>
  );
}
