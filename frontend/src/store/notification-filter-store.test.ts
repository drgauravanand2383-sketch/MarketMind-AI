import { beforeEach, describe, expect, it } from "vitest";
import { ALL_NOTIFICATION_DOMAINS, useNotificationFilterStore } from "@/store/notification-filter-store";

describe("notification-filter-store", () => {
  beforeEach(() => {
    useNotificationFilterStore.getState().resetFilters();
  });

  it("defaults to every domain, no filters, empty search", () => {
    const state = useNotificationFilterStore.getState();
    expect(state.domains).toEqual(ALL_NOTIFICATION_DOMAINS);
    expect(state.readFilter).toBe("all");
    expect(state.priority).toBe("");
    expect(state.search).toBe("");
  });

  it("toggleDomain removes and re-adds a domain", () => {
    useNotificationFilterStore.getState().toggleDomain("alerts");
    expect(useNotificationFilterStore.getState().domains).not.toContain("alerts");

    useNotificationFilterStore.getState().toggleDomain("alerts");
    expect(useNotificationFilterStore.getState().domains).toContain("alerts");
  });

  it("applySnapshot replaces every field at once", () => {
    useNotificationFilterStore.getState().applySnapshot({ domains: ["health"], readFilter: "unread", priority: "HIGH", search: "AAPL" });

    const state = useNotificationFilterStore.getState();
    expect(state.domains).toEqual(["health"]);
    expect(state.readFilter).toBe("unread");
    expect(state.priority).toBe("HIGH");
    expect(state.search).toBe("AAPL");
  });

  it("resetFilters restores every field to its default", () => {
    useNotificationFilterStore.getState().applySnapshot({ domains: ["health"], readFilter: "unread", priority: "HIGH", search: "AAPL" });

    useNotificationFilterStore.getState().resetFilters();

    expect(useNotificationFilterStore.getState()).toMatchObject({ domains: ALL_NOTIFICATION_DOMAINS, readFilter: "all", priority: "", search: "" });
  });
});
