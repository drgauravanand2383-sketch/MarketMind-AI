import { useState, type ReactNode } from "react";
import { Button } from "@/components/button";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { Pagination } from "@/components/table/pagination";
import { CreateWatchlistDialog } from "@/features/watchlists/create-watchlist-dialog";
import { RenameWatchlistDialog } from "@/features/watchlists/rename-watchlist-dialog";
import { WatchlistFiltersBar } from "@/features/watchlists/watchlist-filters";
import { WatchlistTable } from "@/features/watchlists/watchlist-table";
import { useDeleteWatchlist, useDuplicateWatchlist, useWatchlistsList } from "@/hooks/use-watchlists";
import { useWatchlistUiStore } from "@/store/watchlist-ui-store";
import type { Watchlist, WatchlistListParams } from "@/types/watchlist";

export function WatchlistListPage(): ReactNode {
  const filters = useWatchlistUiStore((state) => state.filters);
  const sort = useWatchlistUiStore((state) => state.sort);
  const direction = useWatchlistUiStore((state) => state.direction);
  const page = useWatchlistUiStore((state) => state.page);
  const pageSize = useWatchlistUiStore((state) => state.pageSize);
  const setPage = useWatchlistUiStore((state) => state.setPage);

  const params: WatchlistListParams = {
    page,
    page_size: pageSize,
    sort,
    direction,
    ...(filters.name && { name: filters.name }),
    ...(filters.sector && { sector: filters.sector }),
    ...(filters.country && { country: filters.country }),
    ...(filters.theme && { theme: filters.theme }),
    ...(filters.ticker && { ticker: filters.ticker }),
  };

  const list = useWatchlistsList(params);
  const deleteWatchlist = useDeleteWatchlist();
  const duplicateWatchlist = useDuplicateWatchlist();

  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Watchlist | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Watchlist | null>(null);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Watchlists</h1>
        <Button
          onClick={() => {
            setCreateOpen(true);
          }}
        >
          Create watchlist
        </Button>
      </div>

      <WatchlistFiltersBar />

      {list.isPending && <SkeletonList rows={5} rowClassName="h-12 w-full" />}

      {list.isError && (
        <ErrorState
          title="Couldn't load watchlists"
          message={list.error.message}
          onRetry={() => {
            void list.refetch();
          }}
        />
      )}

      {list.isSuccess && list.data.data.length === 0 && (
        <EmptyState
          title="No watchlists found"
          description={
            [filters.name, filters.sector, filters.country, filters.theme, filters.ticker].some((value) => value.length > 0)
              ? "No watchlists match your current search and filters."
              : "Create your first watchlist to start tracking companies."
          }
        />
      )}

      {list.isSuccess && list.data.data.length > 0 && (
        <>
          <WatchlistTable
            watchlists={list.data.data}
            onRename={setRenameTarget}
            onDuplicate={(watchlist) => {
              duplicateWatchlist.mutate(watchlist);
            }}
            onDelete={setDeleteTarget}
          />
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPageChange={setPage} />
        </>
      )}

      <CreateWatchlistDialog
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
        }}
      />

      <RenameWatchlistDialog
        watchlist={renameTarget}
        onClose={() => {
          setRenameTarget(null);
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete watchlist"
        message={`Delete "${deleteTarget?.name ?? ""}"? This permanently removes it and every company tracked within it.`}
        confirmLabel="Delete"
        destructive
        isLoading={deleteWatchlist.isPending}
        onCancel={() => {
          setDeleteTarget(null);
        }}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteWatchlist.mutate(deleteTarget.id, {
            onSuccess: () => {
              setDeleteTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
