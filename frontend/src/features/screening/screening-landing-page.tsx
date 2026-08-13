import { useEffect, useState, type ReactNode } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Panel } from "@/components/panel";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { Pagination } from "@/components/table/pagination";
import { CreateScreeningProfileDialog } from "@/features/screening/create-screening-profile-dialog";
import { DuplicateScreeningProfileDialog } from "@/features/screening/duplicate-screening-profile-dialog";
import { RecentScreeningRunsList } from "@/features/screening/recent-screening-runs-list";
import { RenameScreeningProfileDialog } from "@/features/screening/rename-screening-profile-dialog";
import { ScreeningProfileTable } from "@/features/screening/screening-profile-table";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useDeleteScreeningProfile, useScreeningProfilesList } from "@/hooks/use-screening";
import { useScreeningUiStore } from "@/store/screening-ui-store";
import type { ListScreeningProfilesParams, ScreeningProfile } from "@/types/screening";

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

export function ScreeningLandingPage(): ReactNode {
  const nameSearch = useScreeningUiStore((state) => state.nameSearch);
  const sort = useScreeningUiStore((state) => state.sort);
  const direction = useScreeningUiStore((state) => state.direction);
  const page = useScreeningUiStore((state) => state.page);
  const pageSize = useScreeningUiStore((state) => state.pageSize);
  const setNameSearch = useScreeningUiStore((state) => state.setNameSearch);
  const setPage = useScreeningUiStore((state) => state.setPage);

  const [localSearch, setLocalSearch] = useState(nameSearch);
  const debouncedSearch = useDebouncedValue(localSearch);

  useEffect(() => {
    setNameSearch(debouncedSearch);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setNameSearch is a stable store action
  }, [debouncedSearch]);

  const params: ListScreeningProfilesParams = {
    page,
    page_size: pageSize,
    sort,
    direction,
    ...(nameSearch && { name: nameSearch }),
  };

  const list = useScreeningProfilesList(params);
  const deleteProfile = useDeleteScreeningProfile();

  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<ScreeningProfile | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<ScreeningProfile | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ScreeningProfile | null>(null);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Screening</h1>
        <button
          type="button"
          onClick={() => {
            setCreateOpen(true);
          }}
          className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Create screen
        </button>
      </div>

      <div>
        <label htmlFor="screening-search" className="sr-only">
          Search screening profiles by name
        </label>
        <input
          id="screening-search"
          type="search"
          data-shortcut-target="search"
          placeholder="Search screens by name…"
          value={localSearch}
          onChange={(event) => {
            setLocalSearch(event.target.value);
          }}
          className={`${INPUT_CLASS} w-full max-w-sm`}
        />
      </div>

      {list.isPending && <SkeletonList rows={5} rowClassName="h-12 w-full" />}

      {list.isError && (
        <ErrorState
          title="Couldn't load screening profiles"
          message={list.error.message}
          onRetry={() => {
            void list.refetch();
          }}
        />
      )}

      {list.isSuccess && list.data.data.length === 0 && (
        <EmptyState
          title="No screens found"
          description={nameSearch ? "No screens match your search." : "Create your first screen to start screening companies."}
        />
      )}

      {list.isSuccess && list.data.data.length > 0 && (
        <>
          <ScreeningProfileTable
            profiles={list.data.data}
            onRename={setRenameTarget}
            onDuplicate={setDuplicateTarget}
            onDelete={setDeleteTarget}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPageChange={setPage} />
        </>
      )}

      <Panel title="Recent screening runs (this session)">
        <RecentScreeningRunsList />
      </Panel>

      <CreateScreeningProfileDialog
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
        }}
      />

      <RenameScreeningProfileDialog
        profile={renameTarget}
        onClose={() => {
          setRenameTarget(null);
        }}
      />

      <DuplicateScreeningProfileDialog
        profile={duplicateTarget}
        onClose={() => {
          setDuplicateTarget(null);
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete screen"
        message={`Delete "${deleteTarget?.name ?? ""}"? This permanently removes the screen and its filters.`}
        confirmLabel="Delete"
        destructive
        isLoading={deleteProfile.isPending}
        onCancel={() => {
          setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteProfile.mutate(deleteTarget.id, {
            onSuccess: () => {
              setDeleteTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
