import { createFileRoute } from "@tanstack/react-router";
import { WatchlistDetailPage } from "@/features/watchlists/watchlist-detail-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/watchlists/$watchlistId")({
  beforeLoad: requirePermission("watchlist:read"),
  component: RouteComponent,
});

function RouteComponent() {
  const { watchlistId } = Route.useParams();
  return <WatchlistDetailPage watchlistId={watchlistId} />;
}
