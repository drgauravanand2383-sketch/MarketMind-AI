import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog } from "@/components/dialog";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useUpdateScreeningProfile } from "@/hooks/use-screening";
import type { ScreeningProfile } from "@/types/screening";

const renameProfileSchema = z.object({
  name: z.string().min(1, "Name is required"),
});

type RenameProfileValues = z.infer<typeof renameProfileSchema>;

export function RenameScreeningProfileDialog({
  profile,
  onClose,
}: {
  profile: ScreeningProfile | null;
  onClose: () => void;
}): ReactNode {
  const updateProfile = useUpdateScreeningProfile(profile?.id ?? "");
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RenameProfileValues>({
    resolver: zodResolver(renameProfileSchema),
    values: { name: profile?.name ?? "" },
  });

  const onSubmit = handleSubmit((values) => {
    updateProfile.mutate(values, {
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
    <Dialog open={profile !== null} onClose={handleClose} title="Rename screen">
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
          <LoadingButton isLoading={updateProfile.isPending} loadingText="Saving…">
            Save
          </LoadingButton>
        </div>
      </form>
    </Dialog>
  );
}
