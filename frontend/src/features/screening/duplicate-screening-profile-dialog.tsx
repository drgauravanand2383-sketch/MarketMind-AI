import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog } from "@/components/dialog";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useDuplicateScreeningProfile } from "@/hooks/use-screening";
import type { ScreeningProfile } from "@/types/screening";

const duplicateProfileSchema = z.object({
  new_name: z.string().min(1, "Name is required"),
});

type DuplicateProfileValues = z.infer<typeof duplicateProfileSchema>;

export function DuplicateScreeningProfileDialog({
  profile,
  onClose,
}: {
  profile: ScreeningProfile | null;
  onClose: () => void;
}): ReactNode {
  const duplicateProfile = useDuplicateScreeningProfile();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<DuplicateProfileValues>({
    resolver: zodResolver(duplicateProfileSchema),
    values: { new_name: profile ? `${profile.name} (copy)` : "" },
  });

  const onSubmit = handleSubmit((values) => {
    if (!profile) return;
    duplicateProfile.mutate(
      { profileId: profile.id, body: values },
      {
        onSuccess: () => {
          onClose();
        },
      },
    );
  });

  function handleClose(): void {
    reset();
    onClose();
  }

  return (
    <Dialog open={profile !== null} onClose={handleClose} title="Duplicate screen">
      <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4" noValidate>
        <FormField label="New name" autoComplete="off" error={errors.new_name?.message} {...register("new_name")} />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <LoadingButton isLoading={duplicateProfile.isPending} loadingText="Duplicating…">
            Duplicate
          </LoadingButton>
        </div>
      </form>
    </Dialog>
  );
}
