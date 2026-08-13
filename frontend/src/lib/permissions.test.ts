import { beforeEach, describe, expect, it } from "vitest";
import { isRedirect } from "@tanstack/react-router";
import { hasPermission, requirePermission } from "@/lib/permissions";
import { useAuthStore } from "@/store/auth-store";
import { testUser } from "@/test/msw/fixtures";

describe("permissions", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null, sessionExpired: false });
  });

  it("hasPermission is false when there is no signed-in user", () => {
    expect(hasPermission("watchlist:read")).toBe(false);
  });

  it("hasPermission reflects the signed-in user's permission list", () => {
    useAuthStore.setState({ user: { ...testUser, permissions: ["watchlist:read"] } });

    expect(hasPermission("watchlist:read")).toBe(true);
    expect(hasPermission("backtest:run")).toBe(false);
  });

  it("requirePermission's guard throws a redirect to /forbidden when the permission is missing", () => {
    useAuthStore.setState({ user: { ...testUser, permissions: [] } });
    const guard = requirePermission("watchlist:read");

    let caught: unknown;
    try {
      guard();
    } catch (error) {
      caught = error;
    }

    expect(isRedirect(caught)).toBe(true);
    expect((caught as { options: { to: string } }).options.to).toBe("/forbidden");
  });

  it("requirePermission's guard does not throw when the permission is present", () => {
    useAuthStore.setState({ user: { ...testUser, permissions: ["watchlist:read"] } });
    const guard = requirePermission("watchlist:read");

    expect(() => {
      guard();
    }).not.toThrow();
  });
});
