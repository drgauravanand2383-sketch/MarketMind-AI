import { createFileRoute } from "@tanstack/react-router";
import { ScreeningResultsPage } from "@/features/screening/screening-results-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/screening/results/$resultId")({
  beforeLoad: requirePermission("screening:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { resultId } = Route.useParams();
  return <ScreeningResultsPage resultId={resultId} />;
}
