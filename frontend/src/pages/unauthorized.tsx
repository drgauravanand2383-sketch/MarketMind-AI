import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { StatusPage } from "@/components/states/status-page";
import { redirectSearchSchema } from "@/lib/route-search";

export const Route = createFileRoute("/unauthorized")({
  validateSearch: redirectSearchSchema,
  component: UnauthorizedPage,
});

function UnauthorizedPage(): ReactNode {
  const { redirect: redirectTo } = Route.useSearch();

  return (
    <StatusPage
      code="401"
      title="Session expired"
      description="Your session has ended or you're not signed in. Please sign in again to continue."
      action={{ label: "Go to login", to: "/login", ...(redirectTo !== undefined && { search: { redirect: redirectTo } }) }}
    />
  );
}
