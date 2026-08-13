import { create } from "zustand";

export interface RecentResearchEntry {
  requestId: string;
  companyName: string;
  ticker: string | null;
  matched: boolean;
  ranAt: string;
}

export interface RecentScreeningEntry {
  resultId: string;
  profileId: string;
  profileName: string;
  companyCount: number;
  matchedCount: number;
  ranAt: string;
}

interface SessionActivityState {
  recentResearch: RecentResearchEntry[];
  recentScreeningRuns: RecentScreeningEntry[];
  addResearch: (entry: RecentResearchEntry) => void;
  addScreeningRun: (entry: RecentScreeningEntry) => void;
  clear: () => void;
}

const MAX_RECENT = 10;

/**
 * This browser session's own research/screening activity only — not a
 * durable history. Neither Company Research reports nor Screening run
 * results are persisted server-side (`InMemoryResultStore`, cleared on
 * backend restart, no list endpoint — see
 * `docs/architecture/INTELLIGENCE_API.md` §2), so there is nothing to
 * fetch a real history from. By explicit product decision (Milestone 4),
 * this is deliberately NOT persisted to `localStorage` and must be
 * labeled in the UI as "this session" — implying durability the backend
 * doesn't provide would be misleading.
 */
export const useSessionActivityStore = create<SessionActivityState>()((set) => ({
  recentResearch: [],
  recentScreeningRuns: [],

  addResearch: (entry) => {
    set((state) => ({ recentResearch: [entry, ...state.recentResearch].slice(0, MAX_RECENT) }));
  },
  addScreeningRun: (entry) => {
    set((state) => ({ recentScreeningRuns: [entry, ...state.recentScreeningRuns].slice(0, MAX_RECENT) }));
  },
  clear: () => {
    set({ recentResearch: [], recentScreeningRuns: [] });
  },
}));
