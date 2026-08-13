import { createFileRoute } from "@tanstack/react-router";
import { ExplainabilityDetailPage } from "@/features/historical-analysis/explainability/explainability-detail-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/explainability/$requestId")({
  beforeLoad: requirePermission("explainability:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { requestId } = Route.useParams();
  return <ExplainabilityDetailPage requestId={requestId} />;
}
