import { createFileRoute } from "@tanstack/react-router";
import { BacktestDetailPage } from "@/features/historical-analysis/backtesting/backtest-detail-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/backtests/$runId")({
  beforeLoad: requirePermission("backtest:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { runId } = Route.useParams();
  return <BacktestDetailPage runId={runId} />;
}
