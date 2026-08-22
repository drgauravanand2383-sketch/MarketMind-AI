import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  DECISION_DIGEST_WINDOW_MS,
  useRealtimeNotificationStore,
  type DigestChangeDetail,
  type NotificationCenterEntry,
} from "@/store/realtime-notification-store";
import { usePreferencesStore } from "@/store/preferences-store";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New alert",
    summary: "Something happened.",
    occurredAt: "2026-01-01T00:00:00Z",
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

const T0 = "2026-01-01T10:01:00Z";

function buildDigestChange(overrides: Partial<DigestChangeDetail> = {}): DigestChangeDetail {
  return {
    eventFingerprint: `fp-${String(Math.random())}`,
    domain: "RISK",
    label: "Portfolio A",
    previousValue: "LOW",
    currentValue: "HIGH",
    priority: "HIGH",
    summary: "Portfolio risk for Portfolio A transitioned from LOW to HIGH.",
    occurredAt: T0,
    ...overrides,
  };
}

/** A "decisions"-domain entry as `toNotificationEntry` would build it for
 * a `PORTFOLIO_INTELLIGENCE_CHANGED` event — the shape `addEntry`'s
 * v1.2 Priority 3 digest logic actually branches on. */
function buildDecisionEntry(overrides: Partial<NotificationCenterEntry> = {}, changeOverrides: Partial<DigestChangeDetail> = {}): NotificationCenterEntry {
  const change = buildDigestChange({ occurredAt: overrides.occurredAt ?? T0, ...changeOverrides });
  return {
    id: `evt-${String(Math.random())}`,
    eventType: "PORTFOLIO_INTELLIGENCE_CHANGED",
    domain: "decisions",
    priority: change.priority,
    title: `${change.label}: ${change.domain.toLowerCase()} changed`,
    summary: change.summary,
    occurredAt: change.occurredAt,
    read: false,
    entityRef: { kind: "decision", portfolioId: "wl-a" },
    groupKey: change.eventFingerprint,
    pendingDigestChange: change,
    ...overrides,
  };
}

/** Selects the stable `entries` array and filters in the component body
 * — exactly the pattern every consumer of this store must use (see the
 * store's own docstring) — as a regression test against the M6
 * `useSyncExternalStore` "getSnapshot should be cached" infinite-loop
 * footgun. */
function UnreadCount(): ReactNode {
  const entries = useRealtimeNotificationStore((state) => state.entries);
  const unread = entries.filter((entry) => !entry.read).length;
  return <span>{unread} unread</span>;
}

describe("realtime-notification-store", () => {
  it("addEntry prepends and caps at 200 entries", () => {
    useRealtimeNotificationStore.setState({ entries: [] });
    for (let i = 0; i < 205; i += 1) {
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: `entry-${String(i)}` }));
    }

    const entries = useRealtimeNotificationStore.getState().entries;
    expect(entries).toHaveLength(200);
    expect(entries[0]?.id).toBe("entry-204"); // newest first
  });

  it("markRead marks exactly one entry read", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a" }), buildEntry({ id: "b" })] });

    useRealtimeNotificationStore.getState().markRead("a");

    const entries = useRealtimeNotificationStore.getState().entries;
    expect(entries.find((e) => e.id === "a")?.read).toBe(true);
    expect(entries.find((e) => e.id === "b")?.read).toBe(false);
  });

  it("markAllRead marks every entry read", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a" }), buildEntry({ id: "b" })] });

    useRealtimeNotificationStore.getState().markAllRead();

    expect(useRealtimeNotificationStore.getState().entries.every((e) => e.read)).toBe(true);
  });

  it("clear empties the list", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry()] });

    useRealtimeNotificationStore.getState().clear();

    expect(useRealtimeNotificationStore.getState().entries).toEqual([]);
  });

  it("a component filtering `entries` in its body (not inside the selector) renders without an infinite-loop error", () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ read: false }), buildEntry({ read: true })] });

    render(<UnreadCount />);

    expect(screen.getByText("1 unread")).toBeInTheDocument();
  });

  // --- v1.2 Priority 2: cross-portfolio notification grouping -----------------------------------------------------------

  describe("group-aware addEntry", () => {
    it("three arrivals sharing one groupKey collapse into a single entry (§8 item 1)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1", summary: "Dell moved.", affectedPortfolioCount: 3 })
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t1", summary: "Dell moved.", affectedPortfolioCount: 3 })
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildEntry({ id: "e3", groupKey: "MARKET:dell:price:t1", summary: "Dell moved.", affectedPortfolioCount: 3 })
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.affectedPortfolioCount).toBe(3);
    });

    it("a single arrival with a groupKey still produces exactly one entry (§8 item 2)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });

    it("different groupKeys never collapse into each other (§8 item 3)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t2" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });

    it("a market event and a news event for the same entity stay separate entries (§8 item 5)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2", groupKey: "NEWS:dell:count:5" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });

    it("entries without a groupKey keep the pre-v1.2 unconditional-prepend behavior (§8 item 10)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });

    it("a later arrival for an already-read group does not reset it to unread (§8 item 11)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1", read: false }));
      useRealtimeNotificationStore.getState().markRead("e1");

      useRealtimeNotificationStore.getState().addEntry(
        buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t1", read: false, affectedPortfolioCount: 2 })
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.read).toBe(true);
      expect(entries[0]?.affectedPortfolioCount).toBe(2);
    });

    it("a grouped entry moves to the top of the list on a later arrival", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "other" }));

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t1" }));

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
      expect(entries[0]?.id).toBe("e2");
    });
  });

  // --- v1.2 Priority 3: Portfolio Decision Digest -----------------------------------------------------------

  describe("Portfolio Decision Digest", () => {
    it("one decision event produces one digest entry of length 1 (§10 item 1)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry());

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes).toHaveLength(1);
    });

    it("two different domains for the same portfolio within the window fold into one digest (§10 item 2)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RISK", previousValue: "LOW", currentValue: "HIGH" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION", previousValue: "HOLD", currentValue: "BUY", label: "AAPL" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes).toHaveLength(2);
      expect(entries[0]?.title).toBe("2 decision changes affecting Portfolio A");
    });

    it("three events within the window fold into one digest, all three preserved (§10 item 3/§3)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RISK", previousValue: "LOW", currentValue: "HIGH" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION", previousValue: "HOLD", currentValue: "BUY", label: "AAPL" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:04:00Z" }, { domain: "STRATEGY", previousValue: "62.0", currentValue: "74.0" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      const digest = entries[0]?.digest;
      expect(digest?.changes).toHaveLength(3);
      expect(digest?.changes.map((c) => c.domain)).toEqual(["RISK", "RECOMMENDATION", "STRATEGY"]);
      expect(entries[0]?.summary).toBe("Risk: LOW → HIGH; Recommendation: HOLD → BUY; Strategy: 62.0 → 74.0");
      expect(entries[0]?.occurredAt).toBe("2026-01-01T10:04:00Z"); // newest change's timestamp
    });

    it("an event after the window creates a new digest instead of extending the old one (§10 item 4)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      const start = Date.parse(T0);

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: T0 }, { domain: "RISK" }));
      const afterWindow = new Date(start + DECISION_DIGEST_WINDOW_MS + 1000).toISOString();
      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: afterWindow }, { domain: "RECOMMENDATION" }));

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
      expect(entries[0]?.digest?.changes).toHaveLength(1);
      expect(entries[1]?.digest?.changes).toHaveLength(1);
    });

    it("different portfolio ids never share a digest (§10 item 5)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ entityRef: { kind: "decision", portfolioId: "wl-a" } }, { domain: "RISK" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ entityRef: { kind: "decision", portfolioId: "wl-b" } }, { domain: "RISK" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
    });

    it("different companies coexist in the same portfolio's digest (§10 item 6)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RECOMMENDATION", label: "AAPL" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION", label: "MSFT" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes.map((c) => c.label)).toEqual(["AAPL", "MSFT"]);
    });

    it("digest priority is the highest of its contained changes (§10 item 7/§5)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "STRATEGY", priority: "LOW" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION", priority: "MEDIUM" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:03:00Z" }, { domain: "RISK", priority: "HIGH" }),
      );

      expect(useRealtimeNotificationStore.getState().entries[0]?.priority).toBe("HIGH");
    });

    it("an already-read digest is not reset to unread by a later compatible event (§10 item 8)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RISK" }));
      const digestId = useRealtimeNotificationStore.getState().entries[0]?.id;
      if (digestId !== undefined) useRealtimeNotificationStore.getState().markRead(digestId);

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.read).toBe(true);
    });

    it("alert entries are never folded into a decision digest (§10 item 10)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RISK" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "alert-1", domain: "alerts" }));

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
      expect(entries.some((e) => e.domain === "alerts" && e.digest === undefined)).toBe(true);
    });

    it("backtest entries are never folded into a decision digest (§10 item 11)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:01:00Z" }, { domain: "RISK" }));
      useRealtimeNotificationStore.getState().addEntry(
        buildEntry({ id: "bt-1", domain: "backtests", eventType: "BACKTEST_COMPLETED", entityRef: { kind: "backtest", runId: "run-1" } }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
      expect(entries.find((e) => e.id === "bt-1")?.digest).toBeUndefined();
    });

    it("the same event_fingerprint redelivered does not duplicate inside a digest (§10 item 14)", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      const change = buildDigestChange({ eventFingerprint: "RISK:wl-a:HIGH", domain: "RISK" });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({}, change));
      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({}, change));
      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({}, change));

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes).toHaveLength(1);
    });

    it("a decision entry with no known portfolio (portfolio-agnostic) is never digested", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ entityRef: { kind: "decision", portfolioId: null } }, { domain: "RISK" }),
      );

      expect(useRealtimeNotificationStore.getState().entries[0]?.digest).toBeUndefined();
    });
  });

  // --- v1.2 Priority 4: Notification & Intelligence Preferences -----------------------------------------------------------

  describe("groupCrossPortfolioNotifications preference", () => {
    afterEach(() => {
      usePreferencesStore.getState().resetAll();
    });

    it("default (true) still collapses same-groupKey arrivals", () => {
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t1" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });

    it("false shows one Notification Center row per arrival, even sharing a groupKey", () => {
      usePreferencesStore.getState().setGroupCrossPortfolioNotifications(false);
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e1", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e2", groupKey: "MARKET:dell:price:t1" }));
      useRealtimeNotificationStore.getState().addEntry(buildEntry({ id: "e3", groupKey: "MARKET:dell:price:t1" }));

      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(3);
    });
  });

  describe("decisionDigestWindowMinutes preference", () => {
    afterEach(() => {
      usePreferencesStore.getState().resetAll();
    });

    it("a new digest created while the window is 1 minute does not fold a change arriving 2 minutes later", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(1);
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:00:00Z" }, { domain: "RISK" }));
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z" }, { domain: "RECOMMENDATION" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2);
    });

    it("a new digest created while the window is 20 minutes folds a change arriving 10 minutes later", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(20);
      useRealtimeNotificationStore.setState({ entries: [] });

      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:00:00Z" }, { domain: "RISK" }));
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:10:00Z" }, { domain: "RECOMMENDATION" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes).toHaveLength(2);
    });

    it("changing the setting mid-window does not alter an already-open digest's own window", () => {
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(20);
      useRealtimeNotificationStore.setState({ entries: [] });

      // Digest opens with a 20-minute window locked in.
      useRealtimeNotificationStore.getState().addEntry(buildDecisionEntry({ occurredAt: "2026-01-01T10:00:00Z" }, { domain: "RISK" }));

      // User narrows the setting to 1 minute while the digest is still open.
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(1);

      // A change 10 minutes later would fail a fresh 1-minute check, but the
      // digest's own locked-in 20-minute window still folds it in.
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:10:00Z" }, { domain: "RECOMMENDATION" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(1);
      expect(entries[0]?.digest?.changes).toHaveLength(2);
    });

    it("a digest created after the setting change uses the new window", () => {
      useRealtimeNotificationStore.setState({ entries: [] });
      usePreferencesStore.getState().setDecisionDigestWindowMinutes(1);

      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:00:00Z", entityRef: { kind: "decision", portfolioId: "wl-new" } }, { domain: "RISK" }),
      );
      useRealtimeNotificationStore.getState().addEntry(
        buildDecisionEntry({ occurredAt: "2026-01-01T10:02:00Z", entityRef: { kind: "decision", portfolioId: "wl-new" } }, { domain: "RECOMMENDATION" }),
      );

      const entries = useRealtimeNotificationStore.getState().entries;
      expect(entries).toHaveLength(2); // 2 minutes > the newly-configured 1-minute window
    });
  });
});
