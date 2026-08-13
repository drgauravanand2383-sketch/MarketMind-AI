import { useState, type ReactNode } from "react";
import { Panel } from "@/components/panel";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { ScreeningBuilder } from "@/features/screening/builder/screening-builder";
import { RenameScreeningProfileDialog } from "@/features/screening/rename-screening-profile-dialog";
import { RunScreeningPanel } from "@/features/screening/run-screening-panel";
import { useScreeningProfile, useUpdateScreeningProfile } from "@/hooks/use-screening";

export function ScreeningProfileDetailPage({ profileId }: { profileId: string }): ReactNode {
  const profile = useScreeningProfile(profileId);
  const updateProfile = useUpdateScreeningProfile(profileId);
  const [renameOpen, setRenameOpen] = useState(false);

  if (profile.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={5} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (profile.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this screen"
          message={profile.error.message}
          onRetry={() => {
            void profile.refetch();
          }}
        />
      </div>
    );
  }

  const data = profile.data;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{data.name}</h1>
          {data.description && <p className="text-sm text-slate-600 dark:text-slate-300">{data.description}</p>}
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Created {new Date(data.created_at).toLocaleDateString()} · Updated {new Date(data.updated_at).toLocaleDateString()}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setRenameOpen(true);
          }}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Rename
        </button>
      </div>

      <Panel title="Builder">
        <ScreeningBuilder
          key={data.id}
          filters={data.filters}
          groups={data.groups}
          isSaving={updateProfile.isPending}
          onSave={(filters, groups) => {
            updateProfile.mutate({ filters, groups });
          }}
        />
      </Panel>

      <Panel title="Run this screen">
        <RunScreeningPanel profile={data} />
      </Panel>

      <RenameScreeningProfileDialog
        profile={renameOpen ? data : null}
        onClose={() => {
          setRenameOpen(false);
        }}
      />
    </div>
  );
}
