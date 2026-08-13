import { useEffect, useRef } from "react";
import { useDecisionHistoryStore } from "@/store/decision-history-store";
import { notify } from "@/store/notification-store";
import type { RiskAssessment } from "@/types/portfolio";

/** Fires the "Risk loaded" notification and a `risk_loaded` decision-
 * history entry the first time a given `RiskAssessment.request_id`
 * appears, and again only if a genuinely new one loads later — never on
 * a re-render of the same data. Risk has no `POST` endpoint
 * (`docs/architecture/INTELLIGENCE_API.md` — GET-only) and TanStack
 * Query v5 dropped `useQuery`'s `onSuccess`, so a plain query has no
 * other natural place to hang this side effect off of. */
export function useRiskLoadedEffects(assessment: RiskAssessment | undefined, portfolioId: string): void {
  const lastRequestId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!assessment || lastRequestId.current === assessment.request_id) return;
    lastRequestId.current = assessment.request_id;
    notify("success", "Risk assessment loaded.");
    useDecisionHistoryStore.getState().addEntry({
      kind: "risk_loaded",
      id: assessment.request_id,
      portfolioId,
      requestId: assessment.request_id,
      occurredAt: assessment.generated_at,
    });
  }, [assessment, portfolioId]);
}
