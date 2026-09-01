import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, waitFor } from "@testing-library/react";
import { useRealtimeSync } from "@/hooks/use-realtime-sync";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { buildDomainEvent, buildEventEnvelope, installFakeWebSocket } from "@/test/mock-websocket";
import { buildAlert, buildBacktestResult, buildDetectedChange, buildIntelligenceRun, testUser } from "@/test/msw/fixtures";
import { globalMarketsKeys } from "@/hooks/use-global-markets";
import { useAuthStore } from "@/store/auth-store";
import { useNotificationStore } from "@/store/notification-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";

describe("useRealtimeSync", () => {
  let lastSocket: ReturnType<typeof installFakeWebSocket>["lastSocket"];

  beforeEach(() => {
    ({ lastSocket } = installFakeWebSocket());
    useAuthStore.setState({
      user: { ...testUser, permissions: ["alerts:read", "backtest:read", "portfolio:read", "strategy:read", "explainability:read", "global_markets:read"] },
    });
    useNotificationStore.setState({ notifications: [] });
    usePreferencesStore.getState().resetAll();
    useRealtimeNotificationStore.setState({ entries: [] });
    useRealtimeConnectionStore.setState({ state: "disconnected", lastEventAt: null, lastHeartbeatAt: null, reconnect: () => {} });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("mirrors connection state into realtime-connection-store", () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
    });

    expect(useRealtimeConnectionStore.getState().state).toBe("connected");
  });

  it("on an ALERT_GENERATED event: invalidates the alerts list, records a notification entry, and fires a toast", async () => {
    const { queryClient } = renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert({ priority: "CRITICAL", ticker: "AAPL" }))));
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["alerts", "list"] });
    });
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    expect(useRealtimeNotificationStore.getState().entries[0]?.domain).toBe("alerts");
    const toast = useNotificationStore.getState().notifications[0];
    expect(toast?.type).toBe("error"); // CRITICAL priority
  });

  it("on a BACKTEST_COMPLETED event: surgically invalidates that run's queries", async () => {
    const { queryClient } = renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("BACKTEST_COMPLETED", buildBacktestResult({ request_id: "run-9" }))));
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["backtests", "run", "run-9"] });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["backtests", "results", "run-9"] });
  });

  it("on a GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED event: invalidates the latest-run and per-run caches, records a notification entry, and fires a success toast for a COMPLETED run", async () => {
    const { queryClient } = renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(
        buildEventEnvelope(buildDomainEvent("GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED", buildIntelligenceRun({ id: "run-9", status: "COMPLETED" }))),
      );
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: globalMarketsKeys.latestRun() });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: globalMarketsKeys.run("run-9") });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: globalMarketsKeys.runs(), exact: true });
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    expect(useRealtimeNotificationStore.getState().entries[0]?.domain).toBe("global_markets");
    const toast = useNotificationStore.getState().notifications[0];
    expect(toast?.type).toBe("success");
  });

  it("on a GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED event with FAILED status: fires a pinned error toast, never a misleading success", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(
        buildEventEnvelope(
          buildDomainEvent(
            "GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED",
            buildIntelligenceRun({
              id: "run-10",
              status: "FAILED",
              category_outcomes: [
                { category: "INDIA_EQUITY", succeeded: false, market_session_context: null, error: "provider unavailable" },
              ],
            }),
          ),
        ),
      );
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    expect(useRealtimeNotificationStore.getState().entries[0]?.priority).toBe("CRITICAL");
    const toast = useNotificationStore.getState().notifications[0];
    expect(toast?.type).toBe("error");
  });

  it("a RISK_ASSESSMENT_COMPLETED event (never sent by the real backend, but simulated here) produces no notification entry", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(
        buildEventEnvelope(
          buildDomainEvent("RISK_ASSESSMENT_COMPLETED", {
            request_id: "risk-1",
            overall_risk_score: 40,
            overall_severity: "MODERATE",
            risk_metrics: [],
            exposures: [],
            recommendations: [],
            summary: "Moderate risk.",
            generated_at: "2026-01-01T00:00:00Z",
          }),
        ),
      );
    });

    await waitFor(() => {
      expect(useRealtimeConnectionStore.getState().lastEventAt).not.toBeNull();
    });
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(0);
  });

  it("fires a pinned error toast exactly once the connection transitions to 'failed' after exhausting the default retry budget", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    vi.useFakeTimers();

    // `useWebSocket` constructs its `WebSocketClient` with default
    // options (`maxReconnectAttempts: 5`, `reconnectBaseDelayMs: 1000`)
    // — drive it through all 5 scheduled reconnects (exhaustive
    // exponential-backoff coverage itself lives in `ws-client.test.ts`;
    // here we only need to reach "failed" once to confirm the toast).
    let delay = 1_000;
    for (let attempt = 0; attempt < 5; attempt += 1) {
      act(() => {
        lastSocket().onclose?.();
      });
      act(() => {
        vi.advanceTimersByTime(delay);
      });
      delay *= 2;
    }
    // 6th close: attempts (5) >= maxReconnectAttempts (5) -> "failed".
    act(() => {
      lastSocket().onclose?.();
    });
    vi.useRealTimers();

    await waitFor(() => {
      expect(useRealtimeConnectionStore.getState().state).toBe("failed");
    });
    const toasts = useNotificationStore.getState().notifications.filter((n) => n.type === "error");
    expect(toasts).toHaveLength(1);
  });

  it("suppresses the Notification Center entry and toast for a disabled category, while still invalidating caches", async () => {
    usePreferencesStore.getState().toggleNotificationCategory("alerts");
    const { queryClient } = renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert())));
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["alerts", "list"] });
    });
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(0);
    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("fires a desktop Notification when enabled and permission is granted", async () => {
    usePreferencesStore.getState().setDesktopNotificationsEnabled(true);
    const created: { title: string; body?: string }[] = [];
    class FakeNotification {
      static permission = "granted";
      constructor(
        public title: string,
        options?: { body?: string },
      ) {
        created.push({ title, ...(options?.body !== undefined && { body: options.body }) });
      }
    }
    vi.stubGlobal("Notification", FakeNotification);

    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert({ ticker: "AAPL" }))));
    });

    await waitFor(() => {
      expect(created).toHaveLength(1);
    });
    expect(created[0]?.title).toContain("AAPL");
  });

  it("does not fire a desktop Notification when the preference is off, even if permission is granted", async () => {
    const created: { title: string }[] = [];
    class FakeNotification {
      static permission = "granted";
      constructor(public title: string) {
        created.push({ title });
      }
    }
    vi.stubGlobal("Notification", FakeNotification);

    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert())));
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    expect(created).toHaveLength(0);
  });

  // --- v1.2 Priority 2: cross-portfolio notification grouping (§8 item 12) -----------------------------------------------------------

  it("collapses three SIGNIFICANT_MARKET_CHANGE arrivals sharing one event_fingerprint into a single Notification Center entry and a single toast", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    const change = (portfolioId: string) =>
      buildDetectedChange({
        domain: "MARKET", label: "Dell", priority: "HIGH", portfolio_id: portfolioId,
        event_fingerprint: "MARKET:dell:price:t1", impacted_portfolio_ids: ["wl-a", "wl-b", "wl-c"],
      });

    act(() => {
      lastSocket().simulateOpen();
    });
    act(() => {
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change("wl-a"))));
    });
    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    act(() => {
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change("wl-b"))));
    });
    act(() => {
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change("wl-c"))));
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries[0]?.affectedPortfolioCount).toBe(3);
    });
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    expect(useNotificationStore.getState().notifications).toHaveLength(1);
  });

  it("still produces separate Notification Center entries for two genuinely different events (different event_fingerprint)", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", buildDetectedChange({ event_fingerprint: "MARKET:dell:price:t1" })))
      );
    });
    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", buildDetectedChange({ event_fingerprint: "MARKET:dell:price:t2" })))
      );
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });
  });

  // --- v1.2 Priority 3: Portfolio Decision Digest (§10) -----------------------------------------------------------

  it("real Risk + Recommendation + Strategy events for one portfolio fold into a single deep-linkable digest", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(
          buildDomainEvent(
            "PORTFOLIO_INTELLIGENCE_CHANGED",
            buildDetectedChange({ domain: "RISK", label: "Portfolio A", portfolio_id: "wl-a", event_fingerprint: "RISK:wl-a:HIGH", priority: "HIGH" }),
            { timestamp: "2026-01-01T10:01:00Z" },
          ),
        ),
      );
    });
    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(
          buildDomainEvent(
            "PORTFOLIO_INTELLIGENCE_CHANGED",
            buildDetectedChange({ domain: "RECOMMENDATION", label: "AAPL", portfolio_id: "wl-a", event_fingerprint: "RECOMMENDATION:wl-a:AAPL", priority: "MEDIUM" }),
            { timestamp: "2026-01-01T10:02:00Z" },
          ),
        ),
      );
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(
          buildDomainEvent(
            "PORTFOLIO_INTELLIGENCE_CHANGED",
            buildDetectedChange({ domain: "STRATEGY", label: "Portfolio A", portfolio_id: "wl-a", event_fingerprint: "STRATEGY:wl-a:74", priority: "LOW" }),
            { timestamp: "2026-01-01T10:04:00Z" },
          ),
        ),
      );
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries[0]?.digest?.changes).toHaveLength(3);
    });
    const digestEntry = useRealtimeNotificationStore.getState().entries[0];
    expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1); // one digest, not three entries
    expect(digestEntry?.title).toBe("3 decision changes affecting Portfolio A");
    expect(digestEntry?.priority).toBe("HIGH"); // highest of LOW/MEDIUM/HIGH
    expect(digestEntry?.entityRef).toEqual({ kind: "decision", portfolioId: "wl-a" }); // unchanged deep-link target
  });

  it("a decision event for a different portfolio never joins another portfolio's digest (composes correctly with Priority-2 scoping)", async () => {
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(buildDomainEvent("PORTFOLIO_INTELLIGENCE_CHANGED", buildDetectedChange({ domain: "RISK", portfolio_id: "wl-a", event_fingerprint: "RISK:wl-a:HIGH" }))),
      );
    });
    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    act(() => {
      lastSocket().simulateMessage(
        buildEventEnvelope(buildDomainEvent("PORTFOLIO_INTELLIGENCE_CHANGED", buildDetectedChange({ domain: "RISK", portfolio_id: "wl-b", event_fingerprint: "RISK:wl-b:HIGH" }))),
      );
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });
    const portfolioIds = useRealtimeNotificationStore.getState().entries.map((e) => e.digest?.portfolioId);
    expect(new Set(portfolioIds)).toEqual(new Set(["wl-a", "wl-b"]));
  });

  // --- v1.2 Priority 4: Notification & Intelligence Preferences -----------------------------------------------------------

  it("showRealtimeToasts=false suppresses the toast but the Notification Center entry still arrives and stays unread-tracked", async () => {
    usePreferencesStore.getState().setShowRealtimeToasts(false);
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert({ priority: "CRITICAL", ticker: "AAPL" }))));
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    expect(useRealtimeNotificationStore.getState().entries[0]?.read).toBe(false);
    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("showRealtimeToasts=false does not affect desktop notifications, which keep their own separate toggle", async () => {
    usePreferencesStore.getState().setShowRealtimeToasts(false);
    usePreferencesStore.getState().setDesktopNotificationsEnabled(true);
    const created: { title: string }[] = [];
    class FakeNotification {
      static permission = "granted";
      constructor(public title: string) {
        created.push({ title });
      }
    }
    vi.stubGlobal("Notification", FakeNotification);

    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert({ ticker: "AAPL" }))));
    });

    await waitFor(() => {
      expect(created).toHaveLength(1);
    });
    expect(useNotificationStore.getState().notifications).toHaveLength(0);
  });

  it("groupCrossPortfolioNotifications=false fires a separate toast for each portfolio's copy of the same event_fingerprint", async () => {
    usePreferencesStore.getState().setGroupCrossPortfolioNotifications(false);
    renderHookWithQueryClient(() => {
      useRealtimeSync();
    });

    // Distinct `summary` per arrival — `notify()` itself dedups identical
    // (type, message) pairs regardless of grouping (`notification-store.ts`);
    // using the same summary for both would test that unrelated dedup, not
    // the `groupCrossPortfolioNotifications` gate this test targets.
    const change = (portfolioId: string) =>
      buildDetectedChange({
        domain: "MARKET", label: "Dell", priority: "HIGH", portfolio_id: portfolioId,
        event_fingerprint: "MARKET:dell:price:t1", impacted_portfolio_ids: ["wl-a", "wl-b"],
        summary: `Dell moved (seen via ${portfolioId}).`,
      });

    act(() => {
      lastSocket().simulateOpen();
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change("wl-a"))));
    });
    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(1);
    });
    act(() => {
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("SIGNIFICANT_MARKET_CHANGE", change("wl-b"))));
    });

    await waitFor(() => {
      expect(useRealtimeNotificationStore.getState().entries).toHaveLength(2);
    });
    expect(useNotificationStore.getState().notifications).toHaveLength(2);
  });

  it("ALERT_GENERATED handling is unaffected by the decision-digest code path (§10 item 10)", async () => {
    const { queryClient } = renderHookWithQueryClient(() => {
      useRealtimeSync();
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    act(() => {
      lastSocket().simulateOpen();
    });
    act(() => {
      lastSocket().simulateMessage(buildEventEnvelope(buildDomainEvent("ALERT_GENERATED", buildAlert({ priority: "HIGH", ticker: "AAPL" }))));
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["alerts", "list"] });
    });
    const entries = useRealtimeNotificationStore.getState().entries;
    expect(entries).toHaveLength(1);
    expect(entries[0]?.digest).toBeUndefined();
  });
});
