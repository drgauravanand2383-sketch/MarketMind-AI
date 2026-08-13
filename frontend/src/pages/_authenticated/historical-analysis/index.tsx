import { createFileRoute } from "@tanstack/react-router";
import { HistoricalAnalysisLandingPage } from "@/features/historical-analysis/historical-analysis-landing-page";
import { getNavItem } from "@/lib/nav-items";
import { requirePermission } from "@/lib/permissions";

const item = getNavItem("/historical-analysis");

export const Route = createFileRoute("/_authenticated/historical-analysis/")({
  beforeLoad: requirePermission(item.permission),
  component: HistoricalAnalysisLandingPage,
});
