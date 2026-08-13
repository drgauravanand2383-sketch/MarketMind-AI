import { createFileRoute } from "@tanstack/react-router";
import { ResearchComparePage } from "@/features/research/research-compare-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/research/compare")({
  beforeLoad: requirePermission("research:read"),
  component: ResearchComparePage,
});
