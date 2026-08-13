import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useRealtimeSubscriptions } from "@/hooks/use-realtime-subscriptions";
import { useAuthStore } from "@/store/auth-store";
import { testUser } from "@/test/msw/fixtures";

describe("useRealtimeSubscriptions", () => {
  it("always includes HEALTH_STATUS_CHANGED, even with zero permissions", () => {
    useAuthStore.setState({ user: { ...testUser, permissions: [] } });

    const { result } = renderHook(() => useRealtimeSubscriptions());

    expect(result.current).toEqual(["HEALTH_STATUS_CHANGED"]);
  });

  it("includes only the event types whose required permission the user holds", () => {
    useAuthStore.setState({ user: { ...testUser, permissions: ["alerts:read", "backtest:read"] } });

    const { result } = renderHook(() => useRealtimeSubscriptions());

    expect(result.current).toEqual(["HEALTH_STATUS_CHANGED", "ALERT_GENERATED", "BACKTEST_STARTED", "BACKTEST_COMPLETED"]);
  });

  it("never requests RISK_ASSESSMENT_COMPLETED, even with every other permission granted", () => {
    useAuthStore.setState({
      user: { ...testUser, permissions: ["alerts:read", "backtest:read", "portfolio:read", "strategy:read", "explainability:read"] },
    });

    const { result } = renderHook(() => useRealtimeSubscriptions());

    expect(result.current).not.toContain("RISK_ASSESSMENT_COMPLETED");
    expect(result.current).toEqual(
      expect.arrayContaining(["HEALTH_STATUS_CHANGED", "ALERT_GENERATED", "BACKTEST_STARTED", "BACKTEST_COMPLETED", "RECOMMENDATION_GENERATED", "STRATEGY_EVALUATION_COMPLETED", "EXPLAINABILITY_COMPLETED"]),
    );
  });

  it("never subscribes with an empty event_types array (which server-side means 'every type')", () => {
    useAuthStore.setState({ user: null });

    const { result } = renderHook(() => useRealtimeSubscriptions());

    expect(result.current.length).toBeGreaterThan(0);
  });
});
