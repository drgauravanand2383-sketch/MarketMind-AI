import { create } from "zustand";
import type { PriorityLevel } from "@/components/priority-badge";
import { usePreferencesStore } from "@/store/preferences-store";
import type { ChangeDomain } from "@/types/continuous-intelligence";
import type { EventType } from "@/types/websocket";

/** v1.2 Priority 3 (Portfolio Decision Digest) default / fallback: how
 * long, from a digest's first contained change, a later different-domain
 * change for the *same portfolio* still folds into it rather than
 * starting a new one. v1.2 Priority 4 made this user-configurable
 * (`preferences-store.ts`'s `notifications.decisionDigestWindowMinutes`,
 * 1-30 min, default 5) — this constant remains as the literal default
 * value and the safe fallback `getConfiguredDigestWindowMs` clamps to. */
export const DECISION_DIGEST_WINDOW_MS = 5 * 60 * 1000;

/** Reads the user's configured digest window, defensively re-clamped to
 * [1, 30] minutes here too — `preferences-store.ts`'s own setter and
 * rehydration-time sanitizer already guarantee this, but a corrupted
 * direct `localStorage` edit bypassing both is still handled safely
 * rather than producing a negative or absurdly long window. */
function getConfiguredDigestWindowMs(): number {
  const minutes = usePreferencesStore.getState().notifications.decisionDigestWindowMinutes;
  const safeMinutes = Number.isFinite(minutes) ? Math.min(30, Math.max(1, minutes)) : 5;
  return safeMinutes * 60_000;
}

/** Ranks every `PriorityLevel` tier, so this stays fully and safely
 * typed with no cast. `DetectedChange.priority` (a `ChangePriority`,
 * via `toPriorityLevel`) only ever actually produces
 * `LOW`/`MEDIUM`/`HIGH`/`CRITICAL` here — `MODERATE` (a
 * `RiskAssessment.overall_severity` value used elsewhere in the app) is
 * ranked alongside `MEDIUM` only so this table is total; it is never
 * genuinely reachable through this function's real call sites. Not a
 * new severity hierarchy — reuses the same LOW<...<CRITICAL ordering
 * `PriorityBadge`'s own styling table already implies. */
const DECISION_PRIORITY_RANK: Record<PriorityLevel, number> = {
  LOW: 0,
  MODERATE: 1,
  MEDIUM: 1,
  HIGH: 2,
  CRITICAL: 3,
};

function higherPriority(a: PriorityLevel | null, b: PriorityLevel | null): PriorityLevel | null {
  if (a === null) return b;
  if (b === null) return a;
  return DECISION_PRIORITY_RANK[a] >= DECISION_PRIORITY_RANK[b] ? a : b;
}

/** One preserved change inside a digest — every field a human needs to
 * understand *that specific* change without re-deriving it from a
 * merged sentence. Sourced entirely from fields `DetectedChange` (and
 * therefore `toNotificationEntry`) already computes — nothing invented,
 * no raw UUID surfaced (`label` is the company/portfolio display name
 * the backend already resolved, never `entity_id`/`portfolio_id`
 * themselves). */
export interface DigestChangeDetail {
  eventFingerprint: string;
  domain: ChangeDomain;
  label: string;
  previousValue: string | null;
  currentValue: string | null;
  priority: PriorityLevel | null;
  summary: string;
  occurredAt: string;
}

export type NotificationDomain =
  | "alerts"
  | "backtests"
  | "recommendations"
  | "strategy"
  | "explainability"
  | "health"
  | "market"
  | "news"
  | "decisions"
  | "global_markets";

/** Only `backtest`/`explainability` carry an id their own detail route
 * can be built from (`request_id`/`run_id`) — `Alert`, `RecommendationResult`,
 * and `StrategyEvaluationResult` all carry no portfolio/watchlist id and
 * have no standalone detail route (both live only as tabs inside
 * `/decisions/$portfolioId`), so those three deliberately have no
 * deep-linkable reference. Milestone 15's `market`/`news`/`decision` refs
 * carry a `portfolioId` when Decision Impact attached one (deep-links to
 * `/decisions/$portfolioId`); `null` when the change was portfolio-agnostic
 * (no watchlist currently tracks that entity). */
export type NotificationEntityRef =
  | { kind: "alert" }
  | { kind: "recommendation" }
  | { kind: "strategy" }
  | { kind: "backtest"; runId: string }
  | { kind: "explainability"; requestId: string }
  | { kind: "health" }
  | { kind: "market"; portfolioId: string | null }
  | { kind: "news"; portfolioId: string | null }
  | { kind: "decision"; portfolioId: string | null }
  | { kind: "global_markets"; runId: string };

export interface NotificationCenterEntry {
  id: string;
  eventType: Exclude<EventType, "RISK_ASSESSMENT_COMPLETED">;
  domain: NotificationDomain;
  /** `Alert.priority` passthrough for alerts, derived from
   * `ApplicationHealth.state` for health, `null` for domains with no
   * natural priority concept. */
  priority: PriorityLevel | null;
  title: string;
  summary: string;
  occurredAt: string;
  read: boolean;
  entityRef: NotificationEntityRef;
  /** v1.2 Priority 2 (cross-portfolio notification grouping):
   * `DetectedChange.event_fingerprint`, when the backend event carries
   * one (`market`/`news`/`decisions` domains only). Entries sharing one
   * `groupKey` collapse into a single row (`addEntry` upserts rather
   * than appends) instead of one row per impacted portfolio. `undefined`
   * for every other domain — those keep their pre-v1.2 one-row-per-event
   * behavior unchanged. */
  groupKey?: string;
  /** Present (and `> 1`) only when the underlying event impacted more
   * than one portfolio — drives the "Affected: N portfolios" line. */
  affectedPortfolioCount?: number;
  /** v1.2 Priority 3: a fully-formed `DigestChangeDetail` for this
   * specific event, built once in `toNotificationEntry` from fields it
   * already has (`DetectedChange.domain`/`.label`/`.previous_value`/
   * `.current_value`/`.priority`/`.summary`) — `addEntry` folds this
   * into an existing or new digest without needing to re-derive
   * anything from `title`/`summary` text. Present only for a
   * `"decisions"`-domain entry; `undefined` for every other domain. */
  pendingDigestChange?: DigestChangeDetail;
  /** v1.2 Priority 3 (Portfolio Decision Digest): present once this
   * entry represents 1+ decision-domain changes for one portfolio,
   * folded together because they arrived within `DECISION_DIGEST_WINDOW_MS`
   * of the digest's first change. Every entry eligible for digesting
   * (a `"decisions"`-domain entry with a known `portfolioId`) carries
   * one from the moment it's first added — a lone change is simply a
   * digest of length 1, per this milestone's own "first event -> create
   * digest entry" lifecycle. `undefined` for every non-eligible entry
   * (alerts, backtests, market, news, health, ...). */
  digest?: {
    portfolioId: string;
    /** When this digest's *first* change arrived — the anchor
     * `windowMs` is measured from, fixed for the digest's lifetime
     * (never reset by a later change extending it). */
    windowStart: string;
    /** v1.2 Priority 4: the configured digest window, in ms, locked in
     * from `decisionDigestWindowMinutes` at the moment this digest was
     * *created* (its first change). A later change to the setting
     * therefore only ever affects digests created after that change —
     * an already-open digest keeps behaving exactly as the user expected
     * when they saw its first entry, never shifting mid-window. */
    windowMs: number;
    changes: DigestChangeDetail[];
  };
}

/** v1.2 Priority 3: human-readable label per `ChangeDomain` — only
 * `RISK`/`RECOMMENDATION`/`STRATEGY`/`SIGNAL` ever reach a digest
 * (`MARKET`/`NEWS` route through `market`/`news` domains, never
 * `"decisions"`); the fallback exists only so this stays exhaustive
 * without a lint suppression. */
export function decisionDomainLabel(domain: ChangeDomain): string {
  switch (domain) {
    case "RISK":
      return "Risk";
    case "RECOMMENDATION":
      return "Recommendation";
    case "STRATEGY":
      return "Strategy";
    case "SIGNAL":
      return "Signal";
    default:
      return domain;
  }
}

/** RISK/STRATEGY changes carry the portfolio's own display name as
 * `label` (`app.services.continuous_intelligence.detector`'s `label`
 * parameter for those two domains); RECOMMENDATION/SIGNAL carry a
 * company/entity name instead. Prefer a portfolio-named change when the
 * digest has one; never fall back to a raw id. */
function pickPortfolioLabel(changes: DigestChangeDetail[]): string {
  const portfolioNamed = changes.find((c) => c.domain === "RISK" || c.domain === "STRATEGY");
  return portfolioNamed?.label ?? "this portfolio";
}

function buildDigestTitle(changes: DigestChangeDetail[]): string {
  const [only] = changes;
  if (changes.length === 1 && only !== undefined) {
    // Matches this event type's own pre-v1.2/pre-digest single-entry
    // title exactly — a digest of length 1 looks identical to what a
    // user already saw before this milestone.
    return `${only.label}: ${decisionDomainLabel(only.domain).toLowerCase()} changed`;
  }
  return `${String(changes.length)} decision changes affecting ${pickPortfolioLabel(changes)}`;
}

/** One short line per contained change, joined — "Risk: LOW → HIGH;
 * Recommendation: HOLD → BUY; Strategy: 62.0 → 74.0" — falling back to
 * the change's own full sentence only if either value is genuinely
 * absent (never fabricated). No raw UUID ever appears here — `label`
 * on every `DigestChangeDetail` is already a resolved display name. */
function buildDigestSummary(changes: DigestChangeDetail[]): string {
  return changes
    .map((c) => {
      const transition = c.previousValue !== null && c.currentValue !== null ? `${c.previousValue} → ${c.currentValue}` : c.summary;
      return `${decisionDomainLabel(c.domain)}: ${transition}`;
    })
    .join("; ");
}

const MAX_ENTRIES = 200;

interface RealtimeNotificationState {
  entries: NotificationCenterEntry[];
  addEntry: (entry: NotificationCenterEntry) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clear: () => void;
}

/**
 * This browser session's own real-time domain events only — never
 * persisted. The backend's WebSocket framework has no message replay or
 * persistence at all (`docs/architecture/WEBSOCKET_FRAMEWORK.md` §6): a
 * client that (re)connects after an event fires simply never sees it, so
 * there is no durable history to back a real one, the same reasoning
 * `session-activity-store.ts` (M4) and `decision-history-store.ts`
 * (M5/M6) already established for their own domains.
 *
 * Scoped to only the 6 real WS-driven domain events plus health status
 * changes (approved product decision, `docs/frontend/MILESTONE_7.md`) —
 * the ~15 pre-existing non-WS `notify()` toast call sites across
 * Milestones 2-6 (CRUD success/failure, form validation, etc.) are never
 * written here.
 *
 * `entries` is a single stable array reference per unchanged state — any
 * consumer deriving a filtered/derived view (e.g. an unread count) MUST
 * select this array and `.filter()`/`.length` in the component body, never
 * inside the Zustand selector itself. Selecting `state.entries.filter(...)`
 * returns a new array reference every render, which trips React's
 * `useSyncExternalStore` "the result of getSnapshot should be cached"
 * infinite-render-loop detector — hit and fixed 4 times already in
 * Milestone 6 (`historical-analysis-history-list.tsx` and others).
 */
export const useRealtimeNotificationStore = create<RealtimeNotificationState>()((set) => ({
  entries: [],

  addEntry: (entry) => {
    set((state) => {
      // v1.2 Priority 3 (Portfolio Decision Digest): a decisions-domain
      // entry for a known portfolio folds into (or starts) a per-
      // portfolio digest, taking priority over the plain Priority-2
      // groupKey path below — the digest's own per-eventFingerprint
      // dedup (§4 below) supersedes it for these entries. Order matters
      // here exactly as documented in
      // docs/architecture/CONTINUOUS_INTELLIGENCE.md §20: Priority-2's
      // same-event cross-portfolio grouping already happened server-side
      // (this entry is already the collapsed result for its own
      // event_fingerprint); this step only ever combines *different*
      // event_fingerprints for the *same* portfolio.
      if (entry.pendingDigestChange !== undefined && entry.entityRef.kind === "decision" && entry.entityRef.portfolioId !== null) {
        const portfolioId = entry.entityRef.portfolioId;
        const change = entry.pendingDigestChange;
        const arrivedAtMs = Date.parse(entry.occurredAt);

        const existingDigestEntry = state.entries.find((e) => {
          if (e.digest?.portfolioId !== portfolioId) return false;
          return arrivedAtMs - Date.parse(e.digest.windowStart) < e.digest.windowMs;
        });

        if (existingDigestEntry?.digest !== undefined) {
          // §4/test item 14: the same event_fingerprint arriving again
          // (e.g. a redelivered WS frame) replaces its own prior entry
          // in place rather than appearing twice in one digest.
          const existingChangeIndex = existingDigestEntry.digest.changes.findIndex((c) => c.eventFingerprint === change.eventFingerprint);
          const changes =
            existingChangeIndex === -1
              ? [...existingDigestEntry.digest.changes, change]
              : existingDigestEntry.digest.changes.map((c, i) => (i === existingChangeIndex ? change : c));
          const highestPriority = changes.reduce<PriorityLevel | null>((acc, c) => higherPriority(acc, c.priority), null);
          const merged: NotificationCenterEntry = {
            ...existingDigestEntry,
            priority: highestPriority,
            title: buildDigestTitle(changes),
            summary: buildDigestSummary(changes),
            occurredAt: entry.occurredAt, // newest change's timestamp
            digest: { ...existingDigestEntry.digest, changes },
            // `read` intentionally not overridden - preserved from
            // existingDigestEntry, same precedent as Priority-2 grouping.
          };
          const rest = state.entries.filter((e) => e.id !== existingDigestEntry.id);
          return { entries: [merged, ...rest].slice(0, MAX_ENTRIES) };
        }

        // First (or window-expired) decision change for this portfolio
        // — a digest of length 1, per this milestone's own "first event
        // -> create digest entry" lifecycle (§4).
        const newDigestEntry: NotificationCenterEntry = {
          ...entry,
          title: buildDigestTitle([change]),
          summary: buildDigestSummary([change]),
          digest: { portfolioId, windowStart: entry.occurredAt, windowMs: getConfiguredDigestWindowMs(), changes: [change] },
        };
        return { entries: [newDigestEntry, ...state.entries].slice(0, MAX_ENTRIES) };
      }

      // v1.2 Priority 2, gated by v1.2 Priority 4's presentation-only
      // `groupCrossPortfolioNotifications` preference (default true): an
      // entry carrying a `groupKey` replaces (not appends to) any
      // existing entry with the same key — collapses N per-portfolio WS
      // frames for one underlying event into exactly one visible row,
      // moved to the top and refreshed with the latest
      // `affectedPortfolioCount`/timestamp, while preserving its prior
      // `read` state (a user who already read it should not have it
      // silently marked unread again by a later portfolio's copy
      // arriving). Entries with no `groupKey` (every non-grouped domain),
      // or when the preference is off, behave exactly as before this
      // milestone: unconditional prepend, one row per arrival. The
      // preference never touches how many WS frames arrive or anything
      // server-side — purely how this store folds the ones it receives.
      if (entry.groupKey === undefined || !usePreferencesStore.getState().notifications.groupCrossPortfolioNotifications) {
        return { entries: [entry, ...state.entries].slice(0, MAX_ENTRIES) };
      }
      const existing = state.entries.find((e) => e.groupKey === entry.groupKey);
      if (existing === undefined) {
        return { entries: [entry, ...state.entries].slice(0, MAX_ENTRIES) };
      }
      const merged: NotificationCenterEntry = { ...entry, read: existing.read };
      const rest = state.entries.filter((e) => e.groupKey !== entry.groupKey);
      return { entries: [merged, ...rest].slice(0, MAX_ENTRIES) };
    });
  },
  markRead: (id) => {
    set((state) => ({ entries: state.entries.map((entry) => (entry.id === id ? { ...entry, read: true } : entry)) }));
  },
  markAllRead: () => {
    set((state) => ({ entries: state.entries.map((entry) => (entry.read ? entry : { ...entry, read: true })) }));
  },
  clear: () => {
    set({ entries: [] });
  },
}));
