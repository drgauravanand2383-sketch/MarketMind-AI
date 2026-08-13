import { createFileRoute } from "@tanstack/react-router";
import { BacktestComparePage } from "@/features/historical-analysis/comparison/backtest-compare-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/backtests/compare")({
  beforeLoad: requirePermission("backtest:read"),
  component: BacktestComparePage,
});
