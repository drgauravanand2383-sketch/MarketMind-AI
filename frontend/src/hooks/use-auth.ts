import { useMutation } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth-store";
import type { User } from "@/types/auth";

interface LoginCredentials {
  username: string;
  password: string;
  rememberMe?: boolean;
}

/** Login as a TanStack Query mutation — gives components `isPending`/
 * `isError`/`error` for free, while the actual token/user state still
 * lives in `useAuthStore` (server-state mutation, client-state result —
 * exactly the split `docs/frontend/ARCHITECTURE.md` documents). */
export function useLogin() {
  const login = useAuthStore((state) => state.login);
  return useMutation({
    mutationFn: ({ username, password, rememberMe }: LoginCredentials) => login(username, password, rememberMe),
  });
}

export function useLogout() {
  const logout = useAuthStore((state) => state.logout);
  return useMutation({ mutationFn: () => logout() });
}

export function useCurrentUser(): User | null {
  return useAuthStore((state) => state.user);
}

export function useIsAuthenticated(): boolean {
  return useAuthStore((state) => state.status === "authenticated");
}

export function useAuthStatus(): ReturnType<typeof useAuthStore.getState>["status"] {
  return useAuthStore((state) => state.status);
}
