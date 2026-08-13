import { createFileRoute } from "@tanstack/react-router";
import { WorkspaceSettingsPage } from "@/features/settings/workspace-settings-page";

/** No `requirePermission` guard — personalization settings are available
 * to any authenticated user, the same reasoning `/notifications`
 * (Milestone 7) and `/profile` (Milestone 8) already established. */
export const Route = createFileRoute("/_authenticated/settings/")({
  component: WorkspaceSettingsPage,
});
