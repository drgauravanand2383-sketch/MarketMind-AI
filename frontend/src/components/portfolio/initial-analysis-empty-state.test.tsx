import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { InitialAnalysisEmptyState } from "@/components/portfolio/initial-analysis-empty-state";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildInitialAnalysisState, buildMeta } from "@/test/msw/fixtures";
import { server } from "@/test/msw/server";
import { API_BASE_URL } from "@/services/api/config";

describe("InitialAnalysisEmptyState", () => {
  it("shows an ANALYZING state without a retry action", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/wl-1/analysis-status`, () =>
        HttpResponse.json({ data: buildInitialAnalysisState({ status: "ANALYZING" }), meta: buildMeta() }),
      ),
    );
    renderWithQueryClient(<InitialAnalysisEmptyState portfolioId="wl-1" kind="risk assessment" />);

    expect(await screen.findByText("Analyzing — risk assessment in progress")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("shows an UNAVAILABLE state with the backend's own detail text", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/wl-1/analysis-status`, () =>
        HttpResponse.json(
          { data: buildInitialAnalysisState({ status: "UNAVAILABLE", detail: "No companies tracked yet." }), meta: buildMeta() },
        ),
      ),
    );
    renderWithQueryClient(<InitialAnalysisEmptyState portfolioId="wl-1" kind="recommendations" />);

    expect(await screen.findByText("No recommendations yet")).toBeInTheDocument();
    expect(screen.getByText("No companies tracked yet.")).toBeInTheDocument();
  });

  it("shows an ERROR state and retries by calling the trigger endpoint", async () => {
    server.use(
      http.get(`${API_BASE_URL}/portfolio/wl-1/analysis-status`, () =>
        HttpResponse.json(
          { data: buildInitialAnalysisState({ status: "ERROR", detail: "Initial analysis failed: boom" }), meta: buildMeta() },
        ),
      ),
    );
    let triggerCalls = 0;
    server.use(
      http.post(`${API_BASE_URL}/portfolio/wl-1/analysis`, () => {
        triggerCalls += 1;
        return HttpResponse.json(
          { data: buildInitialAnalysisState({ status: "ANALYZING" }), meta: buildMeta() },
          { status: 202 },
        );
      }),
    );
    renderWithQueryClient(<InitialAnalysisEmptyState portfolioId="wl-1" kind="risk assessment" />);

    expect(await screen.findByText("Initial risk assessment failed")).toBeInTheDocument();
    expect(screen.getByText("Initial analysis failed: boom")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => {
      expect(triggerCalls).toBe(1);
    });
  });
});
