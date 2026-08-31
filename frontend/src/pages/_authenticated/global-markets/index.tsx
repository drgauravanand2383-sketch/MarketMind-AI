import { createFileRoute } from "@tanstack/react-router";
import { GlobalMarketsLandingPage } from "@/features/global-markets/global-markets-landing-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/global-markets");

export const Route = createFileRoute("/_authenticated/global-markets/")({
  beforeLoad: requirePermission(item.permission),
  component: GlobalMarketsLandingPage,
});
