import { useState, type ReactNode } from "react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Panel } from "@/components/panel";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { AddCompanyDialog } from "@/features/watchlists/add-company-dialog";
import { CompanyTable } from "@/features/watchlists/company-table";
import { PortfolioIntelligencePanel } from "@/features/watchlists/portfolio-intelligence-panel";
import { PortfolioRecommendationsPanel } from "@/features/watchlists/portfolio-recommendations-panel";
import { PortfolioRiskPanel } from "@/features/watchlists/portfolio-risk-panel";
import { PortfolioSummaryPanel } from "@/features/watchlists/portfolio-summary-panel";
import { RenameWatchlistDialog } from "@/features/watchlists/rename-watchlist-dialog";
import { useRemoveCompany, useUpdateNotes, useWatchlist, useWatchlistSnapshot } from "@/hooks/use-watchlists";

function SnapshotPanel({ watchlistId }: { watchlistId: string }): ReactNode {
  const snapshot = useWatchlistSnapshot(watchlistId);

  if (snapshot.isPending) return <SkeletonList rows={1} rowClassName="h-6 w-full" />;
  if (snapshot.isError) {
    return (
      <ErrorState
        title="Couldn't load snapshot"
        message={snapshot.error.message}
        onRetry={() => {
          void snapshot.refetch();
        }}
      />
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-4 text-sm">
      <span>
        <span className="font-medium text-slate-900 dark:text-slate-100">{snapshot.data.total_companies}</span>{" "}
        <span className="text-slate-500 dark:text-slate-400">companies</span>
      </span>
      <span>
        <span className="font-medium text-slate-900 dark:text-slate-100">
          {snapshot.data.average_confidence === null ? "—" : `${(snapshot.data.average_confidence * 100).toFixed(0)}%`}
        </span>{" "}
        <span className="text-slate-500 dark:text-slate-400">average confidence</span>
      </span>
      <p className="text-slate-600 dark:text-slate-300">{snapshot.data.summary}</p>
    </div>
  );
}

export function WatchlistDetailPage({ watchlistId }: { watchlistId: string }): ReactNode {
  const watchlist = useWatchlist(watchlistId);
  const removeCompany = useRemoveCompany(watchlistId);
  const updateNotes = useUpdateNotes(watchlistId);

  const [renameOpen, setRenameOpen] = useState(false);
  const [addCompanyOpen, setAddCompanyOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  if (watchlist.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={5} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (watchlist.isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load this watchlist"
          message={watchlist.error.message}
          onRetry={() => {
            void watchlist.refetch();
          }}
        />
      </div>
    );
  }

  const data = watchlist.data;

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{data.name}</h1>
          {data.description && <p className="text-sm text-slate-600 dark:text-slate-300">{data.description}</p>}
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Created {new Date(data.created_at).toLocaleDateString()} · Updated {new Date(data.updated_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              setRenameOpen(true);
            }}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={() => {
              setAddCompanyOpen(true);
            }}
            className="rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Add company
          </button>
        </div>
      </div>

      <Panel title="Snapshot">
        <SnapshotPanel watchlistId={watchlistId} />
      </Panel>

      <Panel title="Companies">
        <CompanyTable
          items={data.items}
          onRemove={setRemoveTarget}
          onSaveNotes={(ticker, notes) => {
            updateNotes.mutate({ ticker, notes });
          }}
          removingTicker={removeCompany.isPending ? removeCompany.variables : null}
          savingNotesTicker={updateNotes.isPending ? updateNotes.variables.ticker : null}
        />
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Portfolio summary">
          <PortfolioSummaryPanel portfolioId={watchlistId} />
        </Panel>
        <Panel title="Risk">
          <PortfolioRiskPanel portfolioId={watchlistId} />
        </Panel>
      </div>

      <Panel title="Intelligence">
        <PortfolioIntelligencePanel portfolioId={watchlistId} />
      </Panel>

      <Panel title="Recommendations">
        <PortfolioRecommendationsPanel portfolioId={watchlistId} />
      </Panel>

      <RenameWatchlistDialog
        watchlist={renameOpen ? data : null}
        onClose={() => {
          setRenameOpen(false);
        }}
      />

      <AddCompanyDialog
        watchlistId={watchlistId}
        open={addCompanyOpen}
        onClose={() => {
          setAddCompanyOpen(false);
        }}
      />

      <ConfirmDialog
        open={removeTarget !== null}
        title="Remove company"
        message={`Remove ${removeTarget ?? ""} from this watchlist?`}
        confirmLabel="Remove"
        destructive
        isLoading={removeCompany.isPending}
        onCancel={() => {
          setRemoveTarget(null);
        }}
        onConfirm={() => {
          if (!removeTarget) return;
          removeCompany.mutate(removeTarget, {
            onSuccess: () => {
              setRemoveTarget(null);
            },
          });
        }}
      />
    </div>
  );
}
