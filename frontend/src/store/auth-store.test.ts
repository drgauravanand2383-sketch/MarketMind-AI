import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { buildMeta } from "@/test/msw/fixtures";
import { API_BASE_URL } from "@/services/api/config";
import { useAuthStore } from "@/store/auth-store";

function resetAuthStore(): void {
  useAuthStore.setState({ status: "idle", accessToken: null, refreshToken: null, user: null, sessionExpired: false });
  window.localStorage.clear();
  window.sessionStorage.clear();
}

describe("auth-store", () => {
  beforeEach(() => {
    resetAuthStore();
  });

  it("login stores the access/refresh tokens and user on success", async () => {
    await useAuthStore.getState().login("alice", "password123");

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.accessToken?.token).toBe("test-access-token");
    expect(state.user?.username).toBe("alice");
  });

  it("logout clears the session even though the server request also runs", async () => {
    await useAuthStore.getState().login("alice", "password123");

    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
  });

  it("refresh clears the session and resolves null when the server rejects the refresh token", async () => {
    await useAuthStore.getState().login("alice", "password123");
    server.use(
      http.post(`${API_BASE_URL}/auth/refresh`, () =>
        HttpResponse.json({ error: "domain_error", message: "Invalid refresh token.", meta: buildMeta() }, { status: 401 }),
      ),
    );

    const result = await useAuthStore.getState().refresh();

    expect(result).toBeNull();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("flags sessionExpired when an existing session's refresh fails", async () => {
    await useAuthStore.getState().login("alice", "password123");
    server.use(
      http.post(`${API_BASE_URL}/auth/refresh`, () =>
        HttpResponse.json({ error: "domain_error", message: "Invalid refresh token.", meta: buildMeta() }, { status: 401 }),
      ),
    );

    await useAuthStore.getState().refresh();

    expect(useAuthStore.getState().sessionExpired).toBe(true);
  });

  it("does not flag sessionExpired when there was never a session to expire", async () => {
    const result = await useAuthStore.getState().refresh();

    expect(result).toBeNull();
    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });

  it("logout never leaves sessionExpired set", async () => {
    await useAuthStore.getState().login("alice", "password123");

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });

  it("remember-me on: persists the session in localStorage, not sessionStorage", async () => {
    await useAuthStore.getState().login("alice", "password123", true);

    expect(window.localStorage.getItem("marketmind-auth")).toContain("test-access-token");
    expect(window.sessionStorage.getItem("marketmind-auth")).toBeNull();
  });

  it("remember-me off: persists the session in sessionStorage, not localStorage", async () => {
    await useAuthStore.getState().login("alice", "password123", false);

    expect(window.sessionStorage.getItem("marketmind-auth")).toContain("test-access-token");
    expect(window.localStorage.getItem("marketmind-auth")).toBeNull();
  });
});
