import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { EmptyState } from "@/components/states/empty-state";
import { useDecisionHistoryStore, type DecisionHistoryEntry } from "@/store/decision-history-store";

function describeEntry(entry: DecisionHistoryEntry): { label: string; to?: { to: string; params: Record<string, string> } } {
  switch (entry.kind) {
    case "recommendations_generated":
      return {
        label: `Generated ${String(entry.candidateCount)} recommendations`,
        to: { to: "/decisions/$portfolioId", params: { portfolioId: entry.portfolioId } },
      };
    case "strategy_evaluated":
      return { label: entry.bestStrategy ? `Strategy evaluated — best match: ${entry.bestStrategy}` : "Strategy evaluated" };
    case "risk_loaded":
      return { label: "Risk assessment loaded", to: { to: "/decisions/$portfolioId", params: { portfolioId: entry.portfolioId } } };
    case "signals_evaluated":
      return { label: `Signals evaluated — ${String(entry.triggeredCount)} triggered` };
    case "alerts_evaluated":
      return { label: `Alerts evaluated — ${String(entry.generatedCount)} generated, ${String(entry.suppressedCount)} suppressed` };
  }
}

/** This browser session's own Decision Center activity — see
 * `store/decision-history-store.ts`'s module docstring for why there is
 * no durable, cross-session history to show instead. */
export function DecisionHistoryList(): ReactNode {
  const entries = useDecisionHistoryStore((state) => state.entries);

  if (entries.length === 0) {
    return <EmptyState icon="🕓" title="No decisions made yet this session" description="Generate recommendations, evaluate a strategy, or run a signal/alert evaluation to see it here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry) => {
        const { label, to } = describeEntry(entry);
        return (
          <li key={entry.id} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            {to ? (
              <Link to={to.to} params={to.params} className="text-brand-700 hover:underline dark:text-brand-400">
                {label}
              </Link>
            ) : (
              <span className="text-slate-700 dark:text-slate-300">{label}</span>
            )}
            <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">{new Date(entry.occurredAt).toLocaleString()}</span>
          </li>
        );
      })}
    </ul>
  );
}
