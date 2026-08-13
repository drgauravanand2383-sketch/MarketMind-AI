export interface FeatureNavItem {
  to: string;
  label: string;
  description: string;
  /** The real backend permission string (`RequirePermission`, see
   * `docs/release/API_CONTRACT_V1.md`) that gates viewing this domain —
   * checked client-side by `requirePermission` (`src/lib/permissions.ts`)
   * purely for UX; the backend enforces it independently on every request. */
  permission: string;
  icon: string;
}

/** The single source of truth for the 7 investment-workflow domains —
 * consumed by the sidebar, the dashboard's quick-nav cards, and each
 * domain's own placeholder route, so the label/description/permission
 * for "Watchlists" (etc.) is never typed out more than once. */
export const FEATURE_NAV_ITEMS: FeatureNavItem[] = [
  {
    to: "/watchlists",
    label: "Watchlists",
    description: "Track and manage your investment watchlists.",
    permission: "watchlist:read",
    icon: "📋",
  },
  {
    to: "/research",
    label: "Research",
    description: "Deep-dive company research reports.",
    permission: "research:read",
    icon: "🔍",
  },
  {
    to: "/screening",
    label: "Screening",
    description: "Screen the market against custom criteria.",
    permission: "screening:read",
    icon: "🧮",
  },
  {
    to: "/decisions",
    label: "Decision Center",
    description: "Recommendations, strategy, risk, signals, and alerts in one workspace.",
    permission: "portfolio:read",
    icon: "🧭",
  },
  {
    to: "/historical-analysis",
    label: "Historical Analysis",
    description: "Backtesting, explainability, and performance attribution in one workflow.",
    permission: "backtest:read",
    icon: "🕰",
  },
];

/** Milestone 5 note: `/recommendations` and `/risk` (separate M2-era nav
 * items) were folded into the single `/decisions` Decision Center above
 * — recommendations, strategy, risk, signals, and alerts are now one
 * coherent workspace rather than independent tools, per the milestone's
 * explicit goal.
 *
 * Milestone 6 note: `/backtesting` and `/explainability` (separate M2-era
 * nav items) were folded the same way into `/historical-analysis` — every
 * one of the 7 original investment-workflow domains from Milestone 2 now
 * has a real page; no `ComingSoon` placeholder route remains. */

export function getNavItem(to: string): FeatureNavItem {
  const item = FEATURE_NAV_ITEMS.find((entry) => entry.to === to);
  if (!item) {
    throw new Error(`No nav item registered for "${to}".`);
  }
  return item;
}
