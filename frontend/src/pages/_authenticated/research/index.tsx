import { createFileRoute } from "@tanstack/react-router";
import { ResearchLandingPage } from "@/features/research/research-landing-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/research");

export const Route = createFileRoute("/_authenticated/research/")({
  beforeLoad: requirePermission(item.permission),
  component: ResearchLandingPage,
});
