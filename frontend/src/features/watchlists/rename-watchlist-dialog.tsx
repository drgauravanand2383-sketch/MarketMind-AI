import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog } from "@/components/dialog";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useRenameWatchlist } from "@/hooks/use-watchlists";
import type { Watchlist } from "@/types/watchlist";

const renameWatchlistSchema = z.object({
  name: z.string().min(1, "Name is required"),
});

type RenameWatchlistValues = z.infer<typeof renameWatchlistSchema>;

export function RenameWatchlistDialog({
  watchlist,
  onClose,
}: {
  watchlist: Watchlist | null;
  onClose: () => void;
}): ReactNode {
  const renameWatchlist = useRenameWatchlist(watchlist?.id ?? "");
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RenameWatchlistValues>({
    resolver: zodResolver(renameWatchlistSchema),
    values: { name: watchlist?.name ?? "" },
  });

  const onSubmit = handleSubmit((values) => {
    renameWatchlist.mutate(values, {
      onSuccess: () => {
        onClose();
      },
    });
  });

  function handleClose(): void {
    reset();
    onClose();
  }

  return (
    <Dialog open={watchlist !== null} onClose={handleClose} title="Rename watchlist">
      <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4" noValidate>
        <FormField label="Name" autoComplete="off" error={errors.name?.message} {...register("name")} />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <LoadingButton isLoading={renameWatchlist.isPending} loadingText="Saving…">
            Save
          </LoadingButton>
        </div>
      </form>
    </Dialog>
  );
}
