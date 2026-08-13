import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, waitFor } from "@testing-library/react";
import { useRealtimeSync } from "@/hooks/use-realtime-sync";
import { renderHookWithQueryClient } from "@/test/test-utils";
import { buildDomainEvent, buildEventEnvelope, installFakeWebSocket } from "@/test/mock-websocket";
import { buildAlert, buildBacktestResult, testUser } from "@/test/msw/fixtures";
import { useAuthStore } from "@/store/auth-store";
import { useNotificationStore } from "@/store/notification-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";

describe("useRealtimeSync", () => {
  let lastSocket: ReturnType<typeof installFakeWebSocket>["lastSocket"];

  beforeEach(() => {
    ({ lastSocket } = installFakeWebSocket());
    useAuthStore.setState({ user: { ...testUser, permissions: ["alerts:read", "backtest:read", "portfolio:read", "strategy:read", "explainability:read"] } });
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
});
