import { createFileRoute } from "@tanstack/react-router";
import { ScreeningLandingPage } from "@/features/screening/screening-landing-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/screening");

export const Route = createFileRoute("/_authenticated/screening/")({
  beforeLoad: requirePermission(item.permission),
  component: ScreeningLandingPage,
});
