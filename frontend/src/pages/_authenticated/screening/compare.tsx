import { createFileRoute } from "@tanstack/react-router";
import { ScreeningComparePage } from "@/features/screening/screening-compare-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/screening/compare")({
  beforeLoad: requirePermission("screening:read"),
  component: ScreeningComparePage,
});
