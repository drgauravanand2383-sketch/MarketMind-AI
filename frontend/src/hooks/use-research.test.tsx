import { beforeEach, describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta } from "@/test/msw/fixtures";
import { researchReportStore } from "@/test/msw/handlers";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { API_BASE_URL } from "@/services/api/config";
import { useRunBatchCompanyResearch, useRunCompanyResearch, useResearchReport } from "@/hooks/use-research";
import { useSessionActivityStore } from "@/store/session-activity-store";

describe("use-research", () => {
  beforeEach(() => {
    researchReportStore.reset();
    useSessionActivityStore.setState({ recentResearch: [], recentScreeningRuns: [] });
  });

  it("useRunCompanyResearch runs research and caches the report under its request_id", async () => {
    const { result } = renderHookWithQueryClient(() => useRunCompanyResearch());

    result.current.mutate({ company_name: "Apple Inc.", ticker: "AAPL" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.report.company_overview.company_name).toBe("Apple Inc.");
    expect(result.current.data?.request_id).toBeTruthy();
  });

  it("useRunCompanyResearch records the run in the session-activity store", async () => {
    const { result } = renderHookWithQueryClient(() => useRunCompanyResearch());

    result.current.mutate({ company_name: "Apple Inc.", ticker: "AAPL" });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(useSessionActivityStore.getState().recentResearch).toHaveLength(1);
    expect(useSessionActivityStore.getState().recentResearch[0]?.companyName).toBe("Apple Inc.");
  });

  it("useRunBatchCompanyResearch researches every company in the batch", async () => {
    const { result } = renderHookWithQueryClient(() => useRunBatchCompanyResearch());

    result.current.mutate({ companies: [{ company_name: "Apple Inc." }, { company_name: "Microsoft" }] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toHaveLength(2);
    expect(useSessionActivityStore.getState().recentResearch).toHaveLength(2);
  });

  it("useResearchReport fetches a previously cached report by request_id", async () => {
    const { result: runResult } = renderHookWithQueryClient(() => useRunCompanyResearch());
    runResult.current.mutate({ company_name: "Apple Inc." });
    await waitFor(() => {
      expect(runResult.current.isSuccess).toBe(true);
    });
    const requestId = runResult.current.data?.request_id ?? "";

    const { result } = renderHookWithQueryClient(() => useResearchReport(requestId));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.report.company_overview.company_name).toBe("Apple Inc.");
  });

  it("useResearchReport surfaces a 404 for an id the backend no longer has cached", async () => {
    server.use(
      http.get(`${API_BASE_URL}/research/:requestId`, () =>
        HttpResponse.json({ error: "not_found", message: "Not found.", meta: buildMeta() }, { status: 404 }),
      ),
    );

    const { result } = renderHookWithQueryClient(() => useResearchReport("stale-id"));

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
