import type { HistoricalSnapshot } from "@/types/backtesting";

export interface DraftSnapshot {
  key: string;
  timestamp: string;
  recommendationResultId: string;
  strategyEvaluationId: string;
  riskAssessmentId: string;
  benchmarkValue: string;
}

export function emptySnapshotRow(defaultTimestamp: string): DraftSnapshot {
  return {
    key: crypto.randomUUID(),
    timestamp: defaultTimestamp,
    recommendationResultId: "",
    strategyEvaluationId: "",
    riskAssessmentId: "",
    benchmarkValue: "",
  };
}

export function draftsToSnapshots(drafts: DraftSnapshot[]): HistoricalSnapshot[] {
  return drafts
    .filter((draft) => draft.recommendationResultId.length > 0 && draft.timestamp.length > 0)
    .map((draft) => ({
      timestamp: new Date(draft.timestamp).toISOString(),
      recommendation_result_id: draft.recommendationResultId,
      ...(draft.strategyEvaluationId && { strategy_evaluation_id: draft.strategyEvaluationId }),
      ...(draft.riskAssessmentId && { risk_assessment_id: draft.riskAssessmentId }),
      ...(draft.benchmarkValue && { benchmark_value: Number(draft.benchmarkValue) }),
    }));
}
