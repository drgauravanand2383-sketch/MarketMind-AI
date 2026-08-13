import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { AlertList } from "@/features/decision-center/alerts/alert-list";
import { EvaluateAlertsPanel } from "@/features/decision-center/alerts/evaluate-alerts-panel";
import { usePortfolioRecommendations } from "@/hooks/use-portfolio";

export function AlertsPanel({ portfolioId }: { portfolioId: string }): ReactNode {
  const recommendations = usePortfolioRecommendations(portfolioId);

  return (
    <div className="flex flex-col gap-6">
      <Panel title="Evaluate alerts">
        <EvaluateAlertsPanel />
      </Panel>

      <Panel title="All alerts">
        <AlertList relatedCandidates={recommendations.data?.recommendations} />
      </Panel>
    </div>
  );
}
