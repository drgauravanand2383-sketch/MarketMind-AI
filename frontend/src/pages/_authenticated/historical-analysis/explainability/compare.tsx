import { createFileRoute } from "@tanstack/react-router";
import { ExplainabilityComparePage } from "@/features/historical-analysis/comparison/explainability-compare-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/explainability/compare")({
  beforeLoad: requirePermission("explainability:read"),
  component: ExplainabilityComparePage,
});
