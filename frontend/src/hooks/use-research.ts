import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { researchApi } from "@/services/api/research-api";
import { notify } from "@/store/notification-store";
import { useSessionActivityStore } from "@/store/session-activity-store";
import type {
  BatchCompanyResearchRequest,
  CompanyResearchReportEnvelope,
  CompanyResearchRequest,
} from "@/types/research";

export const researchKeys = {
  all: ["research"] as const,
  detail: (requestId: string) => [...researchKeys.all, "detail", requestId] as const,
};

function describeCompanyCount(count: number): string {
  return `${String(count)} ${count === 1 ? "company" : "companies"}`;
}

function recordResearchActivity(envelope: CompanyResearchReportEnvelope): void {
  useSessionActivityStore.getState().addResearch({
    requestId: envelope.request_id,
    companyName: envelope.report.company_overview.company_name,
    ticker: envelope.report.company_overview.ticker,
    matched: envelope.report.company_overview.matched,
    ranAt: envelope.report.generated_at,
  });
}

/** `GET /research/{request_id}` only ever resolves for an id this same
 * backend process already cached (in-memory store) — a fresh page load
 * pointed at a stale id from a previous process will 404, which callers
 * should render as "no longer available," not a generic error. */
export function useResearchReport(requestId: string) {
  return useQuery({
    queryKey: researchKeys.detail(requestId),
    queryFn: () => researchApi.get(requestId),
    enabled: requestId.length > 0,
  });
}

/** No WebSocket event exists for research progress (`POST /research/company`
 * is synchronous request/response only) — "research started" is this
 * `onMutate` toast, and the mutation's own `isPending` state is what
 * pages/components should use to render an indeterminate loading
 * indicator, not a real multi-step progress bar. */
export function useRunCompanyResearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyResearchRequest) => researchApi.run(body),
    onMutate: (body) => {
      notify("info", `Researching ${body.company_name}...`);
    },
    onSuccess: (envelope) => {
      queryClient.setQueryData(researchKeys.detail(envelope.request_id), envelope);
      recordResearchActivity(envelope);
      notify(
        "success",
        envelope.report.company_overview.matched
          ? `Research complete for ${envelope.report.company_overview.company_name}.`
          : `Research complete — "${envelope.report.company_overview.company_name}" wasn't matched to a known company.`,
      );
    },
  });
}

export function useRunBatchCompanyResearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BatchCompanyResearchRequest) => researchApi.runBatch(body),
    onMutate: (body) => {
      notify("info", `Researching ${describeCompanyCount(body.companies.length)}...`);
    },
    onSuccess: (envelopes) => {
      for (const envelope of envelopes) {
        queryClient.setQueryData(researchKeys.detail(envelope.request_id), envelope);
        recordResearchActivity(envelope);
      }
      notify("success", `Batch research complete for ${describeCompanyCount(envelopes.length)}.`);
    },
  });
}
