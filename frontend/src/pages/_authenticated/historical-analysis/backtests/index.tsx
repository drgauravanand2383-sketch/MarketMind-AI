import { createFileRoute } from "@tanstack/react-router";
import { BacktestExecutionPage } from "@/features/historical-analysis/backtesting/backtest-execution-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/backtests/")({
  beforeLoad: requirePermission("backtest:run"),
  component: BacktestExecutionPage,
});
