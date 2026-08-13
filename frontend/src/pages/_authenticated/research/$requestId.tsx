import { createFileRoute } from "@tanstack/react-router";
import { ResearchResultPage } from "@/features/research/research-result-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/research/$requestId")({
  beforeLoad: requirePermission("research:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { requestId } = Route.useParams();
  return <ResearchResultPage requestId={requestId} />;
}
