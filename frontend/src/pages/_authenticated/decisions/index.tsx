import { createFileRoute } from "@tanstack/react-router";
import { DecisionCenterLandingPage } from "@/features/decision-center/decision-center-landing-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/decisions");

export const Route = createFileRoute("/_authenticated/decisions/")({
  beforeLoad: requirePermission(item.permission),
  component: DecisionCenterLandingPage,
});
