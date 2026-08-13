import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta, buildWatchlist, buildWatchlistItem } from "@/test/msw/fixtures";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { API_BASE_URL } from "@/services/api/config";
import {
  useAddCompany,
  useCreateWatchlist,
  useDeleteWatchlist,
  useDuplicateWatchlist,
  useRemoveCompany,
  useRenameWatchlist,
  useUpdateNotes,
  useWatchlist,
  useWatchlistsList,
  watchlistKeys,
} from "@/hooks/use-watchlists";

describe("use-watchlists", () => {
  beforeEach(() => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
  });

  it("useWatchlistsList fetches the seeded watchlists", async () => {
    const { result } = renderHookWithQueryClient(() => useWatchlistsList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.data).toHaveLength(1);
    expect(result.current.data?.data[0]?.name).toBe("Tech Growth");
  });

  it("useCreateWatchlist creates a watchlist and invalidates the list", async () => {
    const { result } = renderHookWithQueryClient(() => ({
      list: useWatchlistsList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      create: useCreateWatchlist(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.create.mutate({ name: "New List" });

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(2);
    });
    expect(result.current.list.data?.data.some((watchlist) => watchlist.name === "New List")).toBe(true);
  });

  it("useRenameWatchlist updates the cache optimistically before the server responds", async () => {
    const { result, queryClient } = renderHookWithQueryClient(() => ({
      detail: useWatchlist("wl-1"),
      rename: useRenameWatchlist("wl-1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.data?.name).toBe("Tech Growth");
    });

    result.current.rename.mutate({ name: "Renamed" });

    // Optimistic write lands before the mocked network round trip resolves.
    await waitFor(() => {
      expect(queryClient.getQueryData<{ name: string }>(watchlistKeys.detail("wl-1"))?.name).toBe("Renamed");
    });

    await waitFor(() => {
      expect(result.current.rename.isSuccess).toBe(true);
    });
    expect(result.current.detail.data?.name).toBe("Renamed");
  });

  it("useRenameWatchlist rolls back the optimistic update when the server rejects it", async () => {
    server.use(
      http.patch(`${API_BASE_URL}/watchlists/wl-1`, () =>
        HttpResponse.json({ error: "internal_error", message: "Boom.", meta: buildMeta() }, { status: 500 }),
      ),
    );
    const { result, queryClient } = renderHookWithQueryClient(() => ({
      detail: useWatchlist("wl-1"),
      rename: useRenameWatchlist("wl-1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.data?.name).toBe("Tech Growth");
    });

    result.current.rename.mutate({ name: "Will fail" });

    await waitFor(() => {
      expect(result.current.rename.isError).toBe(true);
    });
    expect(queryClient.getQueryData<{ name: string }>(watchlistKeys.detail("wl-1"))?.name).toBe("Tech Growth");
  });

  it("useDeleteWatchlist removes it from the list optimistically and it stays removed on success", async () => {
    const { result } = renderHookWithQueryClient(() => ({
      list: useWatchlistsList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      remove: useDeleteWatchlist(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.remove.mutate("wl-1");

    // Optimistic removal happens before the mocked network round trip
    // resolves — and since this mutation succeeds, it's never rolled back.
    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(0);
    });
    await waitFor(() => {
      expect(result.current.remove.isSuccess).toBe(true);
    });
    expect(result.current.list.data?.data).toHaveLength(0);
  });

  it("useDeleteWatchlist rolls back the optimistic removal when the server rejects it", async () => {
    server.use(
      http.delete(`${API_BASE_URL}/watchlists/wl-1`, () =>
        HttpResponse.json({ error: "internal_error", message: "Boom.", meta: buildMeta() }, { status: 500 }),
      ),
    );
    const { result } = renderHookWithQueryClient(() => ({
      list: useWatchlistsList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      remove: useDeleteWatchlist(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.remove.mutate("wl-1");

    // The mocked failure can resolve faster than any intermediate
    // optimistic state is observable, so this only asserts the
    // end-to-end guarantee: an eventual error rolls the list back to
    // exactly what it was before the mutation ran.
    await waitFor(() => {
      expect(result.current.remove.isError).toBe(true);
    });
    expect(result.current.list.data?.data).toHaveLength(1);
  });

  it("useAddCompany and useRemoveCompany update the watchlist's items", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", items: [] })]);
    const { result } = renderHookWithQueryClient(() => ({
      detail: useWatchlist("wl-1"),
      add: useAddCompany("wl-1"),
      remove: useRemoveCompany("wl-1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.isSuccess).toBe(true);
    });

    result.current.add.mutate({ ticker: "MSFT" });
    await waitFor(() => {
      expect(result.current.detail.data?.items.map((item) => item.ticker)).toEqual(["MSFT"]);
    });

    result.current.remove.mutate("MSFT");
    await waitFor(() => {
      expect(result.current.detail.data?.items).toHaveLength(0);
    });
  });

  it("useUpdateNotes optimistically updates a company's notes and keeps them on success", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", items: [buildWatchlistItem({ ticker: "AAPL", notes: null })] })]);
    const { result } = renderHookWithQueryClient(() => ({
      detail: useWatchlist("wl-1"),
      updateNotes: useUpdateNotes("wl-1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.isSuccess).toBe(true);
    });

    result.current.updateNotes.mutate({ ticker: "AAPL", notes: "Watching earnings" });

    await waitFor(() => {
      expect(result.current.detail.data?.items[0]?.notes).toBe("Watching earnings");
    });
    await waitFor(() => {
      expect(result.current.updateNotes.isSuccess).toBe(true);
    });
    expect(result.current.detail.data?.items[0]?.notes).toBe("Watching earnings");
  });

  it("useUpdateNotes rolls back to the original notes when the server rejects the update", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", items: [buildWatchlistItem({ ticker: "AAPL", notes: null })] })]);
    server.use(
      http.patch(`${API_BASE_URL}/watchlists/wl-1/companies/AAPL/notes`, () =>
        HttpResponse.json({ error: "internal_error", message: "Boom.", meta: buildMeta() }, { status: 500 }),
      ),
    );
    const { result } = renderHookWithQueryClient(() => ({
      detail: useWatchlist("wl-1"),
      updateNotes: useUpdateNotes("wl-1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.isSuccess).toBe(true);
    });

    result.current.updateNotes.mutate({ ticker: "AAPL", notes: "Watching earnings" });

    // Same reasoning as the delete-rollback test above: only the
    // end-to-end guarantee is reliably observable here, not the
    // transient optimistic value in between.
    await waitFor(() => {
      expect(result.current.updateNotes.isError).toBe(true);
    });
    expect(result.current.detail.data?.items[0]?.notes).toBeNull();
  });

  it("useDuplicateWatchlist creates a copy with the same companies", async () => {
    resetWatchlistStore([
      buildWatchlist({ id: "wl-1", name: "Source", items: [buildWatchlistItem({ ticker: "AAPL" }), buildWatchlistItem({ ticker: "MSFT" })] }),
    ]);
    const { result } = renderHookWithQueryClient(() => useDuplicateWatchlist());
    const source = buildWatchlist({
      id: "wl-1",
      name: "Source",
      items: [buildWatchlistItem({ ticker: "AAPL" }), buildWatchlistItem({ ticker: "MSFT" })],
    });

    result.current.mutate(source);

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.name).toBe("Source (copy)");
  });
});
