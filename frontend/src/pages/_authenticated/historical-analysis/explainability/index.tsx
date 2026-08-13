import { createFileRoute } from "@tanstack/react-router";
import { ExplainabilityGeneratePage } from "@/features/historical-analysis/explainability/explainability-generate-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/historical-analysis/explainability/")({
  beforeLoad: requirePermission("explainability:generate"),
  component: ExplainabilityGeneratePage,
});
