import { createFileRoute } from "@tanstack/react-router";
import { ProfilePage } from "@/features/profile/profile-page";

/** No `requirePermission` guard — a user's own profile is available to
 * any authenticated user, the same reasoning `/notifications` (Milestone
 * 7) already established. */
export const Route = createFileRoute("/_authenticated/profile/")({
  component: ProfilePage,
});
