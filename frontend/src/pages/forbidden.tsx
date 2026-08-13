import { createFileRoute } from "@tanstack/react-router";
import { StatusPage } from "@/components/states/status-page";

export const Route = createFileRoute("/forbidden")({
  component: () => (
    <StatusPage
      code="403"
      title="Access denied"
      description="You don't have permission to view this page. Contact an administrator if you believe this is a mistake."
      action={{ label: "Back to dashboard", to: "/" }}
    />
  ),
});
