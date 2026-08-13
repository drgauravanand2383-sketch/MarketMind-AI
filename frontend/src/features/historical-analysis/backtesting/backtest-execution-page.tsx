import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { CreateBacktestForm } from "@/features/historical-analysis/backtesting/create-backtest-form";
import { RunHistoryList } from "@/features/historical-analysis/backtesting/run-history-list";

export function BacktestExecutionPage(): ReactNode {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Run a backtest</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Deterministically replays already-computed recommendation/strategy/risk results across a historical snapshot
          sequence — no live market data or trade simulation is involved.
        </p>
      </div>

      <Panel title="New backtest">
        <CreateBacktestForm />
      </Panel>

      <Panel title="Run history (this session)">
        <RunHistoryList />
      </Panel>
    </div>
  );
}
