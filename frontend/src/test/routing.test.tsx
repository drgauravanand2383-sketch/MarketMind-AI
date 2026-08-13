import { beforeEach, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { routeTree } from "@/app/routeTree.gen";
import { createTestQueryClient } from "@/test/test-utils";
import { buildBacktestResult, buildBacktestRun, buildExplainabilityResult, buildScreeningProfile, buildWatchlist, testUser } from "@/test/msw/fixtures";
import { resetScreeningStore } from "@/test/msw/screening-store";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";
import { resetBacktestingStore, seedBacktest } from "@/test/msw/backtesting-store";
import { resetExplainabilityStore, seedExplainabilityResult } from "@/test/msw/explainability-store";
import { installFakeWebSocket } from "@/test/mock-websocket";
import { useAuthStore } from "@/store/auth-store";
import { useShortcutsStore } from "@/store/shortcuts-store";

async function renderRouterAt(path: string) {
  const router = createRouter({ routeTree, history: createMemoryHistory({ initialEntries: [path] }) });
  // With a real browser history, mounting `RouterProvider` is enough —
  // the initial `popstate`/history subscription kicks off the first
  // match resolution. A `MemoryHistory` starts with its one entry
  // already in place, so no history "change" event ever fires and the
  // router is left in `status: "pending"` with empty `matches` forever
  // unless the initial load is triggered explicitly, here.
  await router.load();
  const queryClient = createTestQueryClient();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, ...result };
}

describe("protected routing (real router, real route guards)", () => {
  beforeEach(() => {
    installFakeWebSocket();
    useAuthStore.setState({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null, sessionExpired: false });
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("redirects an unauthenticated visitor from a protected route to /login", async () => {
    const { router } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
  });

  it("redirects to /unauthorized when the session expired mid-use, not straight to /login", async () => {
    useAuthStore.setState({ sessionExpired: true });
    const { router } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/unauthorized");
    });
  });

  it("redirects to /unauthorized immediately when the session expires mid-use, without waiting for the next navigation", async () => {
    useAuthStore.setState({ status: "authenticated", user: testUser });
    const { router } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });

    useAuthStore.setState({ sessionExpired: true });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/unauthorized");
    });
    // The reactive redirect consumes the flag itself, matching the same
    // once-only handling `_authenticated.tsx`'s `beforeLoad` guard uses.
    expect(useAuthStore.getState().sessionExpired).toBe(false);
  });

  it("redirects an authenticated user lacking the route's permission to /forbidden", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: [] } });
    const { router } = await renderRouterAt("/watchlists");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/forbidden");
    });
  });

  it("redirects an authenticated user lacking the route's permission away from a protected domain route", async () => {
    // Generic permission-gated-route coverage: every domain from Milestone 2
    // now has a real page (no `ComingSoon` placeholder remains after
    // Milestone 6's `/historical-analysis` fold), so the mechanism itself is
    // exercised here against `/historical-analysis` instead of a dedicated
    // placeholder route.
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: [] } });
    const { router } = await renderRouterAt("/historical-analysis");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/forbidden");
    });
  });

  it("sends an already-authenticated visitor away from /login back to /", async () => {
    useAuthStore.setState({ status: "authenticated", user: testUser });
    const { router } = await renderRouterAt("/login");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
  });

  it("renders the dashboard for an authenticated user at /", async () => {
    useAuthStore.setState({ status: "authenticated", user: testUser });
    const { router, findByRole } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(await findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("renders the real watchlist detail page for a permission-holding user", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["watchlist:read"] } });
    const { router, findByRole } = await renderRouterAt("/watchlists/wl-1");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/watchlists/wl-1");
    });
    expect(await findByRole("heading", { name: "Tech Growth" })).toBeInTheDocument();
  });

  it("renders the real research landing page (Milestone 4 — no longer a ComingSoon placeholder)", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["research:read"] } });
    const { router, findByRole } = await renderRouterAt("/research");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/research");
    });
    expect(await findByRole("heading", { name: "Company research" })).toBeInTheDocument();
  });

  it("renders the real screening landing page (Milestone 4 — no longer a ComingSoon placeholder)", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["screening:read"] } });
    const { router, findByRole } = await renderRouterAt("/screening");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/screening");
    });
    expect(await findByRole("heading", { name: "Screening" })).toBeInTheDocument();
  });

  it("renders the real screening profile detail page via its nested $profileId route", async () => {
    resetScreeningStore([buildScreeningProfile({ id: "p1", name: "Large Cap" })]);
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["screening:read"] } });
    const { router, findByRole } = await renderRouterAt("/screening/p1");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/screening/p1");
    });
    expect(await findByRole("heading", { name: "Large Cap" })).toBeInTheDocument();
  });

  it("renders the real Decision Center landing page (Milestone 5 — no longer a ComingSoon placeholder)", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["portfolio:read"] } });
    const { router, findByRole } = await renderRouterAt("/decisions");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/decisions");
    });
    expect(await findByRole("heading", { name: "Decision Center" })).toBeInTheDocument();
  });

  it("renders the real Decision Workspace via its nested $portfolioId route", async () => {
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["portfolio:read"] } });
    const { router, findByRole } = await renderRouterAt("/decisions/wl-1");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/decisions/wl-1");
    });
    expect(await findByRole("heading", { name: "Tech Growth" })).toBeInTheDocument();
    expect(await findByRole("tab", { name: "Overview" })).toBeInTheDocument();
  });

  it("renders the real Historical Analysis landing page (Milestone 6 — no longer a ComingSoon placeholder)", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["backtest:read"] } });
    const { router, findByRole } = await renderRouterAt("/historical-analysis");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/historical-analysis");
    });
    expect(await findByRole("heading", { name: "Historical Analysis" })).toBeInTheDocument();
  });

  it("renders the real backtest execution page via its nested /backtests route", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["backtest:run"] } });
    const { router, findByRole } = await renderRouterAt("/historical-analysis/backtests");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/historical-analysis/backtests");
    });
    expect(await findByRole("heading", { name: "Run a backtest" })).toBeInTheDocument();
  });

  it("renders the real explainability generate page via its nested /explainability route", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["explainability:generate"] } });
    const { router, findByRole } = await renderRouterAt("/historical-analysis/explainability");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/historical-analysis/explainability");
    });
    expect(await findByRole("heading", { name: "Generate an explanation" })).toBeInTheDocument();
  });

  it("renders the real backtest detail page via its nested $runId route", async () => {
    resetBacktestingStore();
    seedBacktest(buildBacktestRun({ request_id: "run-1" }), buildBacktestResult({ request_id: "run-1" }));
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["backtest:read"] } });
    const { router, findByText } = await renderRouterAt("/historical-analysis/backtests/run-1");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/historical-analysis/backtests/run-1");
    });
    expect(await findByText("Run ID run-1")).toBeInTheDocument();
  });

  it("renders the real explainability detail page via its nested $requestId route", async () => {
    resetExplainabilityStore();
    seedExplainabilityResult(buildExplainabilityResult({ request_id: "exp-1" }));
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["explainability:read"] } });
    const { router, findByText } = await renderRouterAt("/historical-analysis/explainability/exp-1");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/historical-analysis/explainability/exp-1");
    });
    expect(await findByText("Request ID exp-1")).toBeInTheDocument();
  });

  it("renders the real Profile page for any authenticated user, no permission required", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: [] } });
    const { router, findByRole } = await renderRouterAt("/profile");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/profile");
    });
    expect(await findByRole("heading", { name: testUser.display_name ?? testUser.username })).toBeInTheDocument();
  });

  it("renders the real Workspace Settings page for any authenticated user, no permission required", async () => {
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: [] } });
    const { router, findByRole } = await renderRouterAt("/settings");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/settings");
    });
    expect(await findByRole("heading", { name: "Workspace settings" })).toBeInTheDocument();
  });
});

describe("keyboard shortcuts (real router, real AppShell)", () => {
  beforeEach(() => {
    installFakeWebSocket();
    useShortcutsStore.persist.clearStorage();
    useShortcutsStore.setState({ helpOpen: false, bindings: useShortcutsStore.getInitialState().bindings });
  });

  it("navigates to a permission-gated domain when its shortcut key is pressed", async () => {
    const user = userEvent.setup();
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["watchlist:read"] } });
    const { router } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });

    await user.keyboard("w");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/watchlists");
    });
  });

  it("does nothing when the shortcut's domain isn't in the user's permissions", async () => {
    const user = userEvent.setup();
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: [] } });
    const { router } = await renderRouterAt("/");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });

    await user.keyboard("w");

    // Give the (absent) navigation a tick to happen if it were going to.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(router.state.location.pathname).toBe("/");
  });

  it("ignores shortcut keys while focus is inside a text field", async () => {
    const user = userEvent.setup();
    resetWatchlistStore([buildWatchlist({ id: "wl-1", name: "Tech Growth" })]);
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["watchlist:read"] } });
    const { router } = await renderRouterAt("/watchlists");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/watchlists");
    });
    const searchInput = await screen.findByLabelText("Search watchlists by name");
    await user.click(searchInput);

    await user.keyboard("w");

    expect(router.state.location.pathname).toBe("/watchlists");
    expect(searchInput).toHaveValue("w");
  });

  it("focuses the current page's own search input on the search shortcut", async () => {
    const user = userEvent.setup();
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["watchlist:read"] } });
    const { router } = await renderRouterAt("/watchlists");
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/watchlists");
    });
    const searchInput = await screen.findByLabelText("Search watchlists by name");
    expect(searchInput).not.toHaveFocus();

    await user.keyboard("/");

    expect(searchInput).toHaveFocus();
  });

  it("opens the shortcuts help dialog on the help shortcut", async () => {
    const user = userEvent.setup();
    useAuthStore.setState({ status: "authenticated", user: testUser });
    await renderRouterAt("/");
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    });

    await user.keyboard("?");

    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });
});
