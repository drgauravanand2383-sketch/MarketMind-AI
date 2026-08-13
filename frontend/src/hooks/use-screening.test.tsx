import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta, buildScreeningProfile } from "@/test/msw/fixtures";
import { screeningResultStore } from "@/test/msw/handlers";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { API_BASE_URL } from "@/services/api/config";
import {
  screeningKeys,
  useCreateScreeningProfile,
  useDeleteScreeningProfile,
  useDuplicateScreeningProfile,
  useRunScreening,
  useScreeningProfile,
  useScreeningProfilesList,
  useScreeningResult,
  useUpdateScreeningProfile,
} from "@/hooks/use-screening";
import type { PaginatedResponse } from "@/types/api";
import type { ScreeningProfile } from "@/types/screening";

describe("use-screening", () => {
  beforeEach(() => {
    resetScreeningStore([buildScreeningProfile({ id: "p1", name: "Large Cap" })]);
    screeningResultStore.reset();
  });

  it("useScreeningProfilesList fetches the seeded profiles", async () => {
    const { result } = renderHookWithQueryClient(() => useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.data).toHaveLength(1);
    expect(result.current.data?.data[0]?.name).toBe("Large Cap");
  });

  it("useCreateScreeningProfile creates a profile and invalidates the list", async () => {
    const { result } = renderHookWithQueryClient(() => ({
      list: useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      create: useCreateScreeningProfile(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.create.mutate({ name: "Value Screen" });

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(2);
    });
  });

  it("useUpdateScreeningProfile updates the cache optimistically before the server responds", async () => {
    const { result, queryClient } = renderHookWithQueryClient(() => ({
      detail: useScreeningProfile("p1"),
      update: useUpdateScreeningProfile("p1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.data?.name).toBe("Large Cap");
    });

    result.current.update.mutate({ name: "Renamed Screen" });

    await waitFor(() => {
      expect(queryClient.getQueryData<ScreeningProfile>(screeningKeys.detail("p1"))?.name).toBe("Renamed Screen");
    });
    await waitFor(() => {
      expect(result.current.update.isSuccess).toBe(true);
    });
  });

  it("useUpdateScreeningProfile rolls back on server rejection", async () => {
    server.use(
      http.patch(`${API_BASE_URL}/screening/profiles/p1`, () =>
        HttpResponse.json({ error: "internal_error", message: "Boom.", meta: buildMeta() }, { status: 500 }),
      ),
    );
    const { result, queryClient } = renderHookWithQueryClient(() => ({
      detail: useScreeningProfile("p1"),
      update: useUpdateScreeningProfile("p1"),
    }));

    await waitFor(() => {
      expect(result.current.detail.data?.name).toBe("Large Cap");
    });

    result.current.update.mutate({ name: "Will fail" });

    await waitFor(() => {
      expect(result.current.update.isError).toBe(true);
    });
    expect(queryClient.getQueryData<ScreeningProfile>(screeningKeys.detail("p1"))?.name).toBe("Large Cap");
  });

  it("useDuplicateScreeningProfile optimistically inserts a temporary row, then reconciles with the server response", async () => {
    const { result, queryClient } = renderHookWithQueryClient(() => ({
      list: useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      duplicate: useDuplicateScreeningProfile(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.duplicate.mutate({ profileId: "p1", body: { new_name: "Large Cap (copy)" } });

    // Optimistic insert lands before the mocked network round trip resolves.
    await waitFor(() => {
      const cached = queryClient.getQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() });
      const total = cached.reduce((sum, [, page]) => sum + (page?.data.length ?? 0), 0);
      expect(total).toBeGreaterThan(1);
    });

    await waitFor(() => {
      expect(result.current.duplicate.isSuccess).toBe(true);
    });
    expect(result.current.duplicate.data?.name).toBe("Large Cap (copy)");
  });

  it("useDuplicateScreeningProfile rolls back the optimistic insert when the server rejects it (name conflict)", async () => {
    resetScreeningStore([
      buildScreeningProfile({ id: "p1", name: "Large Cap" }),
      buildScreeningProfile({ id: "p2", name: "Taken Name" }),
    ]);
    const { result } = renderHookWithQueryClient(() => ({
      list: useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      duplicate: useDuplicateScreeningProfile(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(2);
    });

    result.current.duplicate.mutate({ profileId: "p1", body: { new_name: "Taken Name" } });

    await waitFor(() => {
      expect(result.current.duplicate.isError).toBe(true);
    });
    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(2);
    });
  });

  it("useDeleteScreeningProfile removes it from the list optimistically and it stays removed on success", async () => {
    const { result } = renderHookWithQueryClient(() => ({
      list: useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      remove: useDeleteScreeningProfile(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.remove.mutate("p1");

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(0);
    });
    await waitFor(() => {
      expect(result.current.remove.isSuccess).toBe(true);
    });
  });

  it("useDeleteScreeningProfile rolls back the optimistic removal when the server rejects it", async () => {
    server.use(
      http.delete(`${API_BASE_URL}/screening/profiles/p1`, () =>
        HttpResponse.json({ error: "internal_error", message: "Boom.", meta: buildMeta() }, { status: 500 }),
      ),
    );
    const { result } = renderHookWithQueryClient(() => ({
      list: useScreeningProfilesList({ page: 1, page_size: 20, sort: "updated_at", direction: "desc" }),
      remove: useDeleteScreeningProfile(),
    }));

    await waitFor(() => {
      expect(result.current.list.data?.data).toHaveLength(1);
    });

    result.current.remove.mutate("p1");

    await waitFor(() => {
      expect(result.current.remove.isError).toBe(true);
    });
    expect(result.current.list.data?.data).toHaveLength(1);
  });

  it("useRunScreening evaluates companies against the profile and useScreeningResult re-fetches the cached run", async () => {
    const { result: runResult } = renderHookWithQueryClient(() => useRunScreening("Large Cap"));

    runResult.current.mutate({
      profile_id: "p1",
      companies: [
        { ticker: "AAPL", company_name: "Apple Inc.", market_cap: 2_000_000 },
        { ticker: "TINY", company_name: "Tiny Co", market_cap: 100 },
      ],
    });

    await waitFor(() => {
      expect(runResult.current.isSuccess).toBe(true);
    });
    const passed = new Map(runResult.current.data?.results.map((r) => [r.ticker, r.passed]));
    expect(passed.get("AAPL")).toBe(true);
    expect(passed.get("TINY")).toBe(false);

    const resultId = runResult.current.data?.result_id ?? "";
    const { result: fetched } = renderHookWithQueryClient(() => useScreeningResult(resultId));
    await waitFor(() => {
      expect(fetched.current.isSuccess).toBe(true);
    });
    expect(fetched.current.data?.result_id).toBe(resultId);
  });
});
