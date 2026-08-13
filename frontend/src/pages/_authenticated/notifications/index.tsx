import { createFileRoute } from "@tanstack/react-router";
import { NotificationCenterPage } from "@/features/notifications/notification-center-page";

/** No `requirePermission` guard — unlike the 7 investment-workflow
 * domains, the Notification Center is available to any authenticated
 * user; it reflects only their own WebSocket session. */
export const Route = createFileRoute("/_authenticated/notifications/")({
  component: NotificationCenterPage,
});
