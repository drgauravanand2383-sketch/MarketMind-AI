import { createFileRoute } from "@tanstack/react-router";
import { ResearchBatchPage } from "@/features/research/research-batch-page";
import { requirePermission } from "@/lib/permissions";

export const Route = createFileRoute("/_authenticated/research/batch")({
  beforeLoad: requirePermission("research:run"),
  component: ResearchBatchPage,
});
