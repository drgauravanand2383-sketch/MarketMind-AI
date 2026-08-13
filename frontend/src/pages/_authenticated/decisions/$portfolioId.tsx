import { createFileRoute } from "@tanstack/react-router";
import { DecisionWorkspacePage } from "@/features/decision-center/decision-workspace-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/decisions/$portfolioId")({
  beforeLoad: requirePermission("portfolio:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { portfolioId } = Route.useParams();
  return <DecisionWorkspacePage portfolioId={portfolioId} />;
}
