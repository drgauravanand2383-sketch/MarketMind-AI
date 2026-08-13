import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { watchlistApi } from "@/services/api/watchlist-api";
import { notify } from "@/store/notification-store";
import type { PaginatedResponse } from "@/types/api";
import type {
  AddCompanyRequest,
  CreateWatchlistRequest,
  RenameWatchlistRequest,
  UpdateNotesRequest,
  Watchlist,
  WatchlistListParams,
} from "@/types/watchlist";

export const watchlistKeys = {
  all: ["watchlists"] as const,
  lists: () => [...watchlistKeys.all, "list"] as const,
  list: (params: WatchlistListParams) => [...watchlistKeys.lists(), params] as const,
  details: () => [...watchlistKeys.all, "detail"] as const,
  detail: (id: string) => [...watchlistKeys.details(), id] as const,
  snapshot: (id: string) => [...watchlistKeys.all, "snapshot", id] as const,
};

export function useWatchlistsList(params: WatchlistListParams) {
  return useQuery({
    queryKey: watchlistKeys.list(params),
    queryFn: () => watchlistApi.list(params),
    // Keep showing the previous page's rows while the next page loads,
    // instead of flashing a loading state on every filter/sort/page change.
    placeholderData: (previous) => previous,
  });
}

export function useWatchlist(watchlistId: string) {
  return useQuery({
    queryKey: watchlistKeys.detail(watchlistId),
    queryFn: () => watchlistApi.get(watchlistId),
    enabled: watchlistId.length > 0,
  });
}

export function useWatchlistSnapshot(watchlistId: string) {
  return useQuery({
    queryKey: watchlistKeys.snapshot(watchlistId),
    queryFn: () => watchlistApi.getSnapshot(watchlistId),
    enabled: watchlistId.length > 0,
  });
}

/** Writes `updated` into every cache entry that could be showing this
 * watchlist — the detail query and any currently-cached list page's row
 * — so a rename/notes-edit/company add-or-remove is reflected everywhere
 * it's visible without waiting for a refetch. */
function patchWatchlistInCache(queryClient: QueryClient, updated: Watchlist): void {
  queryClient.setQueryData(watchlistKeys.detail(updated.id), updated);
  queryClient.setQueriesData<PaginatedResponse<Watchlist>>({ queryKey: watchlistKeys.lists() }, (page) => {
    if (!page) return page;
    return { ...page, data: page.data.map((w) => (w.id === updated.id ? updated : w)) };
  });
}

function removeWatchlistFromCache(queryClient: QueryClient, watchlistId: string): void {
  queryClient.removeQueries({ queryKey: watchlistKeys.detail(watchlistId) });
  queryClient.setQueriesData<PaginatedResponse<Watchlist>>({ queryKey: watchlistKeys.lists() }, (page) => {
    if (!page) return page;
    return { ...page, data: page.data.filter((w) => w.id !== watchlistId), total: Math.max(0, page.total - 1) };
  });
}

interface WatchlistMutationSnapshot {
  previousDetail: Watchlist | undefined;
  previousLists: (readonly [readonly unknown[], PaginatedResponse<Watchlist> | undefined])[];
}

/** Snapshots every cache entry `patchWatchlistInCache`/
 * `removeWatchlistFromCache` might touch, for `onError` rollback. Every
 * optimistic mutation below cancels in-flight queries first, so a
 * server response can't land in the middle of an optimistic write and
 * get silently overwritten by it. */
async function snapshotWatchlistCaches(queryClient: QueryClient, watchlistId: string): Promise<WatchlistMutationSnapshot> {
  await queryClient.cancelQueries({ queryKey: watchlistKeys.detail(watchlistId) });
  await queryClient.cancelQueries({ queryKey: watchlistKeys.lists() });
  return {
    previousDetail: queryClient.getQueryData<Watchlist>(watchlistKeys.detail(watchlistId)),
    previousLists: queryClient.getQueriesData<PaginatedResponse<Watchlist>>({ queryKey: watchlistKeys.lists() }),
  };
}

function rollbackWatchlistCaches(queryClient: QueryClient, watchlistId: string, snapshot: WatchlistMutationSnapshot): void {
  if (snapshot.previousDetail) {
    queryClient.setQueryData(watchlistKeys.detail(watchlistId), snapshot.previousDetail);
  }
  for (const [key, data] of snapshot.previousLists) {
    queryClient.setQueryData(key, data);
  }
}

export function useCreateWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateWatchlistRequest) => watchlistApi.create(body),
    onSuccess: (watchlist) => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      notify("success", `Watchlist "${watchlist.name}" created.`);
    },
  });
}

export function useRenameWatchlist(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RenameWatchlistRequest) => watchlistApi.rename(watchlistId, body),
    meta: { suppressErrorToast: true },
    onMutate: async (body): Promise<WatchlistMutationSnapshot> => {
      const snapshot = await snapshotWatchlistCaches(queryClient, watchlistId);
      const optimistic = snapshot.previousDetail
        ? { ...snapshot.previousDetail, name: body.name }
        : undefined;
      if (optimistic) {
        patchWatchlistInCache(queryClient, optimistic);
      } else {
        queryClient.setQueriesData<PaginatedResponse<Watchlist>>({ queryKey: watchlistKeys.lists() }, (page) => {
          if (!page) return page;
          return { ...page, data: page.data.map((w) => (w.id === watchlistId ? { ...w, name: body.name } : w)) };
        });
      }
      return snapshot;
    },
    onError: (_error, _body, snapshot) => {
      if (snapshot) rollbackWatchlistCaches(queryClient, watchlistId, snapshot);
      notify("error", "Couldn't rename the watchlist — change was rolled back.");
    },
    onSuccess: (watchlist) => {
      patchWatchlistInCache(queryClient, watchlist);
      notify("success", `Watchlist renamed to "${watchlist.name}".`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
    },
  });
}

export function useDeleteWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (watchlistId: string) => watchlistApi.delete(watchlistId),
    meta: { suppressErrorToast: true },
    onMutate: async (watchlistId): Promise<WatchlistMutationSnapshot> => {
      const snapshot = await snapshotWatchlistCaches(queryClient, watchlistId);
      removeWatchlistFromCache(queryClient, watchlistId);
      return snapshot;
    },
    onError: (_error, watchlistId, snapshot) => {
      if (snapshot) rollbackWatchlistCaches(queryClient, watchlistId, snapshot);
      notify("error", "Couldn't delete the watchlist — it has been restored.");
    },
    onSuccess: () => {
      notify("success", "Watchlist deleted.");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
    },
  });
}

export function useAddCompany(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddCompanyRequest) => watchlistApi.addCompany(watchlistId, body),
    onSuccess: (watchlist, body) => {
      patchWatchlistInCache(queryClient, watchlist);
      notify("success", `${body.ticker.toUpperCase()} added to "${watchlist.name}".`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
    },
  });
}

export function useRemoveCompany(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => watchlistApi.removeCompany(watchlistId, ticker),
    meta: { suppressErrorToast: true },
    onMutate: async (ticker): Promise<WatchlistMutationSnapshot> => {
      const snapshot = await snapshotWatchlistCaches(queryClient, watchlistId);
      if (snapshot.previousDetail) {
        patchWatchlistInCache(queryClient, {
          ...snapshot.previousDetail,
          items: snapshot.previousDetail.items.filter((item) => item.ticker !== ticker.toUpperCase()),
        });
      }
      return snapshot;
    },
    onError: (_error, _ticker, snapshot) => {
      if (snapshot) rollbackWatchlistCaches(queryClient, watchlistId, snapshot);
      notify("error", "Couldn't remove the company — it has been restored.");
    },
    onSuccess: (watchlist, ticker) => {
      patchWatchlistInCache(queryClient, watchlist);
      notify("success", `${ticker.toUpperCase()} removed.`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
    },
  });
}

export function useUpdateNotes(watchlistId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ticker, notes }: { ticker: string; notes: string }) =>
      watchlistApi.updateNotes(watchlistId, ticker, { notes } satisfies UpdateNotesRequest),
    meta: { suppressErrorToast: true },
    onMutate: async ({ ticker, notes }): Promise<WatchlistMutationSnapshot> => {
      const snapshot = await snapshotWatchlistCaches(queryClient, watchlistId);
      if (snapshot.previousDetail) {
        patchWatchlistInCache(queryClient, {
          ...snapshot.previousDetail,
          items: snapshot.previousDetail.items.map((item) =>
            item.ticker === ticker.toUpperCase() ? { ...item, notes } : item,
          ),
        });
      }
      return snapshot;
    },
    onError: (_error, _vars, snapshot) => {
      if (snapshot) rollbackWatchlistCaches(queryClient, watchlistId, snapshot);
      notify("error", "Couldn't save the note — change was rolled back.");
    },
    onSuccess: (watchlist) => {
      patchWatchlistInCache(queryClient, watchlist);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(watchlistId) });
    },
  });
}

/** Duplicates a watchlist by composing existing endpoints only — create,
 * then add each source company one at a time — since the backend has no
 * "duplicate" endpoint. Deliberately not optimistic: this is several
 * sequential network calls, not a single reversible write, so there's
 * nothing safe to fake locally before the server confirms it. */
export function useDuplicateWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (source: Watchlist) => {
      const copy = await watchlistApi.create({ name: `${source.name} (copy)`, description: source.description });
      for (const item of source.items) {
        await watchlistApi.addCompany(copy.id, {
          ticker: item.ticker,
          company_name: item.company_name,
          country: item.country,
          sector: item.sector,
          theme: item.theme,
          source_agent: item.source_agent,
          confidence: item.confidence,
          reason: item.reason,
          notes: item.notes,
        });
      }
      return copy;
    },
    onSuccess: (copy) => {
      void queryClient.invalidateQueries({ queryKey: watchlistKeys.lists() });
      notify("success", `"${copy.name}" created as a duplicate.`);
    },
    onSettled: (copy) => {
      if (copy) {
        void queryClient.invalidateQueries({ queryKey: watchlistKeys.detail(copy.id) });
      }
    },
  });
}
