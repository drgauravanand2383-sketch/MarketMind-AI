import type { ReactNode } from "react";
import { LoadingButton } from "@/components/forms/loading-button";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { useEvaluateAlerts } from "@/hooks/use-alerts";
import { useSignalResult } from "@/hooks/use-signals";
import { useDecisionHistoryStore } from "@/store/decision-history-store";

/**
 * `POST /alerts/evaluate` requires `SignalResult`s inline — there is no
 * REST endpoint anywhere that produces one server-side except
 * `POST /signals/evaluate` itself. This chains directly off the most
 * recent Signals-tab evaluation in this session (via
 * `useDecisionHistoryStore`, a cache hit against the same query the
 * Signals tab already populated) rather than asking the user to somehow
 * re-supply signals by hand. `rule_ids` is always left empty — no REST
 * endpoint exists to list `AlertRule`s, so "every enabled rule" is the
 * only usable option (see `@/types/alerts`'s module docstring).
 */
export function EvaluateAlertsPanel(): ReactNode {
  const lastSignalsEntry = useDecisionHistoryStore((state) => state.entries.find((entry) => entry.kind === "signals_evaluated"));
  const signalResult = useSignalResult(lastSignalsEntry?.resultId ?? "");
  const evaluateAlerts = useEvaluateAlerts();

  if (!lastSignalsEntry || !signalResult.data) {
    return (
      <EmptyState
        icon="🔔"
        title="Evaluate a signal first"
        description='Alerts are evaluated against SignalResults — run a signal evaluation in the Signals tab, then come back here.'
      />
    );
  }

  const signals = signalResult.data.batch_result.signals;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Ready to evaluate alert rules against the {signals.length} signal {signals.length === 1 ? "result" : "results"} from your
        last Signals evaluation.
      </p>
      <div className="flex items-center gap-3">
        <LoadingButton
          type="button"
          isLoading={evaluateAlerts.isPending}
          loadingText="Evaluating…"
          disabled={signals.length === 0}
          onClick={() => {
            evaluateAlerts.mutate({ signals });
          }}
        >
          Evaluate alerts
        </LoadingButton>
        {evaluateAlerts.isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Evaluating against every enabled rule…
          </p>
        )}
      </div>
      {evaluateAlerts.isError && (
        <ErrorState
          title="Alert evaluation failed"
          message={evaluateAlerts.error.message}
          onRetry={() => {
            evaluateAlerts.mutate(evaluateAlerts.variables);
          }}
        />
      )}
    </div>
  );
}
