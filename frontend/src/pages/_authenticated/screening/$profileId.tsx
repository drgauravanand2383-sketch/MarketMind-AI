import { createFileRoute } from "@tanstack/react-router";
import { ScreeningProfileDetailPage } from "@/features/screening/screening-profile-detail-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/screening/$profileId")({
  beforeLoad: requirePermission("screening:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { profileId } = Route.useParams();
  return <ScreeningProfileDetailPage profileId={profileId} />;
}
