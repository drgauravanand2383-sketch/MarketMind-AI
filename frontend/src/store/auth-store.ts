import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import { authApi } from "@/services/api/auth-api";
import { ApiError } from "@/services/api/errors";
import type { AccessToken, RefreshToken, User } from "@/types/auth";

export type AuthStatus = "idle" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  accessToken: AccessToken | null;
  refreshToken: RefreshToken | null;
  user: User | null;
  /** Set only when an *existing* session's refresh attempt fails (token
   * revoked/expired server-side) — never for "never logged in" or a
   * deliberate `logout()`. Consumed once by `_authenticated.tsx`'s
   * `beforeLoad` to route to `/unauthorized` (an explanatory interstitial)
   * instead of straight to `/login` (the plain credential form). */
  sessionExpired: boolean;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  /** Exchanges the persisted refresh token for a new pair. Returns the
   * new access token string on success, `null` on failure — this exact
   * shape is what `ApiClient`'s `onUnauthorized` hook expects. */
  refresh: () => Promise<string | null>;
}

const REMEMBER_ME_KEY = "marketmind-remember-me";
const AUTH_STORAGE_KEY = "marketmind-auth";

function isAccessTokenExpired(token: AccessToken): boolean {
  return new Date(token.expires_at).getTime() <= Date.now();
}

function getRememberPreference(): boolean {
  return localStorage.getItem(REMEMBER_ME_KEY) !== "false";
}

/** "Remember me" is client-side only (`CLAUDE.md` M2 spec) — the backend
 * issues the same token pair either way. Checked: the session survives a
 * closed browser (`localStorage`). Unchecked: it's gone the moment the
 * tab closes (`sessionStorage`). The flag itself always lives in
 * `localStorage` — it has to be readable synchronously, before we know
 * which of the other two stores to consult, and it carries no session
 * data of its own. */
function setRememberPreference(remember: boolean): void {
  localStorage.setItem(REMEMBER_ME_KEY, String(remember));
  (remember ? sessionStorage : localStorage).removeItem(AUTH_STORAGE_KEY);
}

const dynamicAuthStorage: StateStorage = {
  getItem: (name) => (getRememberPreference() ? localStorage : sessionStorage).getItem(name),
  setItem: (name, value) => {
    (getRememberPreference() ? localStorage : sessionStorage).setItem(name, value);
  },
  removeItem: (name) => {
    localStorage.removeItem(name);
    sessionStorage.removeItem(name);
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      status: "idle",
      accessToken: null,
      refreshToken: null,
      user: null,
      sessionExpired: false,

      login: async (username, password, rememberMe = true) => {
        setRememberPreference(rememberMe);
        const result = await authApi.login({ username, password });
        set({
          status: "authenticated",
          accessToken: result.access_token,
          refreshToken: result.refresh_token,
          user: result.user,
          sessionExpired: false,
        });
      },

      logout: async () => {
        const refreshToken = get().refreshToken;
        try {
          if (refreshToken) {
            await authApi.logout({ refresh_token: refreshToken.token });
          }
        } catch (error) {
          // Logout must always clear local state, even if the network
          // call fails (already-expired token, offline, etc.) — a
          // failed server-side revoke is not a reason to leave the user
          // stuck in an authenticated-looking UI.
          if (!(error instanceof ApiError)) {
            throw error;
          }
        } finally {
          set({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null, sessionExpired: false });
        }
      },

      refresh: async () => {
        const refreshToken = get().refreshToken;
        const hadSession = get().status === "authenticated";
        if (!refreshToken) {
          set({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null });
          return null;
        }
        try {
          const result = await authApi.refresh({ refresh_token: refreshToken.token });
          set({
            status: "authenticated",
            accessToken: result.access_token,
            refreshToken: result.refresh_token,
            user: result.user,
            sessionExpired: false,
          });
          return result.access_token.token;
        } catch {
          set({
            status: "unauthenticated",
            accessToken: null,
            refreshToken: null,
            user: null,
            sessionExpired: hadSession,
          });
          return null;
        }
      },
    }),
    {
      name: AUTH_STORAGE_KEY,
      storage: createJSONStorage(() => dynamicAuthStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        if (state.accessToken && state.refreshToken) {
          state.status = isAccessTokenExpired(state.accessToken) ? "idle" : "authenticated";
        } else {
          state.status = "unauthenticated";
        }
      },
    },
  ),
);

export function getAccessTokenValue(): string | null {
  return useAuthStore.getState().accessToken?.token ?? null;
}

/** Called once at app startup (and by `ApiClient`'s 401 hook): if the
 * persisted access token has expired, attempt one refresh; otherwise
 * resolve immediately. Never throws — a failed refresh just means
 * "unauthenticated", handled by the router's protected-route guard. */
export async function resolveSession(): Promise<void> {
  const { status, accessToken, refresh } = useAuthStore.getState();
  if (status === "idle" && accessToken && isAccessTokenExpired(accessToken)) {
    await refresh();
  } else if (status === "idle") {
    useAuthStore.setState({ status: "unauthenticated" });
  }
}
