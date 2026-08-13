import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "@/test/msw/server";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";
import { resetWatchlistStore } from "@/test/msw/watchlist-store";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // jsdom has no layout engine, so `window.scrollTo` is unimplemented —
  // TanStack Router calls it for scroll restoration on every successful
  // navigation. Stub it so that call is a no-op instead of jsdom's
  // default "not implemented" console error.
  window.scrollTo = () => undefined;
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  // Safety net: a test file that seeds the mock watchlist store
  // (`resetWatchlistStore([...])` in its own `beforeEach`) shouldn't
  // leak mutations into a different file that never seeds it.
  resetWatchlistStore();
  resetDecisionCenterStore();
});

afterAll(() => {
  server.close();
});
