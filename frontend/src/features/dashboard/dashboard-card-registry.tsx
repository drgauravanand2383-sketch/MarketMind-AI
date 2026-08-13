import type { ReactNode } from "react";
import { ConnectivityPanel } from "@/features/dashboard/connectivity-panel";
import { ApiLatencyChart, HealthSummaryChart, ServiceAvailabilityChart } from "@/features/dashboard/charts/lazy-dashboard-charts";
import { HealthPanel } from "@/features/dashboard/health-panel";
import { QuickNavCards } from "@/features/dashboard/quick-nav-cards";
import { RealtimeSummaryCards } from "@/features/dashboard/realtime-summary-cards";
import { RecentActivity } from "@/features/dashboard/recent-activity";
import { UserCard } from "@/features/dashboard/user-card";
import type { DashboardCardId } from "@/types/preferences";

export interface DashboardCardDefinition {
  id: DashboardCardId;
  /** Shown in the customize-mode controls (move/hide buttons) and the
   * Workspace Settings dashboard tab. */
  label: string;
  /** Wrapping `Panel`'s title, rendered as an `<h2>` by `DashboardCardFrame`
   * so every card sits correctly under the page's own `<h1>` — every
   * registered card supplies one (a Milestone 9 audit fix: `RecentActivity`
   * used to render its own internal `<h3>` with no `<h2>` in between). */
  panelTitle?: string;
  render: () => ReactNode;
}

/** The single source of truth for every card the dashboard can show —
 * `dashboard-layout-store.ts`'s `cardOrder`/`hiddenCards`/`cardSizes`
 * all key off `DashboardCardDefinition.id`, and `DashboardPage` renders
 * from this registry rather than hand-listing components, so a card
 * never needs to be wired into layout logic more than once. */
export const DASHBOARD_CARDS: DashboardCardDefinition[] = [
  { id: "user", label: "Account", panelTitle: "Account", render: () => <UserCard /> },
  { id: "connectivity", label: "Connectivity", panelTitle: "Connectivity", render: () => <ConnectivityPanel /> },
  { id: "quick-nav", label: "Quick access", panelTitle: "Quick access", render: () => <QuickNavCards /> },
  { id: "realtime-summary", label: "Session activity", panelTitle: "Session activity", render: () => <RealtimeSummaryCards /> },
  { id: "health-summary-chart", label: "Component health summary", panelTitle: "Component health summary", render: () => <HealthSummaryChart /> },
  { id: "service-availability-chart", label: "Service availability", panelTitle: "Service availability", render: () => <ServiceAvailabilityChart /> },
  { id: "api-latency-chart", label: "API latency", panelTitle: "API latency", render: () => <ApiLatencyChart /> },
  { id: "health-panel", label: "System health", panelTitle: "System health", render: () => <HealthPanel /> },
  { id: "recent-activity", label: "Recent activity", panelTitle: "Recent activity", render: () => <RecentActivity /> },
];

export function getDashboardCard(id: DashboardCardId): DashboardCardDefinition {
  const card = DASHBOARD_CARDS.find((c) => c.id === id);
  if (!card) {
    throw new Error(`No dashboard card registered for "${id}".`);
  }
  return card;
}
