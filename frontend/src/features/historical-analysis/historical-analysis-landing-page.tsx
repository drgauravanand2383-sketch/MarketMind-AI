import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Panel } from "@/components/panel";
import { HistoricalAnalysisHistoryList } from "@/features/historical-analysis/historical-analysis-history-list";

export function HistoricalAnalysisLandingPage(): ReactNode {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Historical Analysis</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Understand how recommendations would have performed historically, why they were produced, and which factors
          contributed most to outcomes — Backtesting, Explainability, and Performance Attribution as one workflow.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Panel title="Backtesting">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Replay already-computed recommendation/strategy/risk results across a historical snapshot sequence and see
            portfolio vs. benchmark performance over time.
          </p>
          <Link
            to="/historical-analysis/backtests"
            className="mt-3 inline-block rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Run a backtest
          </Link>
        </Panel>

        <Panel title="Explainability">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Understand why a recommendation, strategy alignment, or risk assessment came out the way it did — including
            top contributing factors and, optionally, performance attribution for a backtest run.
          </p>
          <Link
            to="/historical-analysis/explainability"
            className="mt-3 inline-block rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Generate an explanation
          </Link>
        </Panel>
      </div>

      <Panel title="History (this session)">
        <HistoricalAnalysisHistoryList />
      </Panel>
    </div>
  );
}
