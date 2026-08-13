import { createFileRoute } from "@tanstack/react-router";
import { WatchlistListPage } from "@/features/watchlists/watchlist-list-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/watchlists");

export const Route = createFileRoute("/_authenticated/watchlists/")({
  beforeLoad: requirePermission(item.permission),
  component: WatchlistListPage,
});
