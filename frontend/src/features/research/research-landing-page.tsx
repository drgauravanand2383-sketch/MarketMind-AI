import type { ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Panel } from "@/components/panel";
import { RecentResearchList } from "@/features/research/recent-research-list";
import { ResearchForm } from "@/features/research/research-form";
import { useRunCompanyResearch } from "@/hooks/use-research";

export function ResearchLandingPage(): ReactNode {
  const navigate = useNavigate();
  const runResearch = useRunCompanyResearch();

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Company research</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Run a deep-dive research report for one company, or research several at once.
          </p>
        </div>
        <Link
          to="/research/batch"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Batch research
        </Link>
      </div>

      <Panel title="Run research">
        <ResearchForm
          isPending={runResearch.isPending}
          onSubmit={(body) => {
            runResearch.mutate(body, {
              onSuccess: (envelope) => {
                void navigate({ to: "/research/$requestId", params: { requestId: envelope.request_id } });
              },
            });
          }}
        />
      </Panel>

      <Panel title="Recent research (this session)">
        <RecentResearchList />
      </Panel>
    </div>
  );
}
