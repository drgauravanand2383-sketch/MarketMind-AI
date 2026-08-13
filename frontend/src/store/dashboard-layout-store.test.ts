import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_CARD_ORDER, useDashboardLayoutStore } from "@/store/dashboard-layout-store";

describe("dashboard-layout-store", () => {
  beforeEach(() => {
    useDashboardLayoutStore.getState().resetLayout();
    useDashboardLayoutStore.setState({ isCustomizing: false });
  });

  it("moveCardUp swaps a card with its predecessor, and is a no-op at the top", () => {
    const [first, second] = useDashboardLayoutStore.getState().cardOrder;

    useDashboardLayoutStore.getState().moveCardUp(second!);
    expect(useDashboardLayoutStore.getState().cardOrder[0]).toBe(second);
    expect(useDashboardLayoutStore.getState().cardOrder[1]).toBe(first);

    const orderBefore = useDashboardLayoutStore.getState().cardOrder;
    useDashboardLayoutStore.getState().moveCardUp(orderBefore[0]!);
    expect(useDashboardLayoutStore.getState().cardOrder).toEqual(orderBefore);
  });

  it("moveCardDown swaps a card with its successor, and is a no-op at the bottom", () => {
    const order = useDashboardLayoutStore.getState().cardOrder;
    const last = order[order.length - 1]!;
    const secondToLast = order[order.length - 2]!;

    useDashboardLayoutStore.getState().moveCardDown(secondToLast);
    const next = useDashboardLayoutStore.getState().cardOrder;
    expect(next[next.length - 1]).toBe(secondToLast);
    expect(next[next.length - 2]).toBe(last);

    // `secondToLast` is now genuinely last — moving it down again must be a no-op.
    useDashboardLayoutStore.getState().moveCardDown(secondToLast);
    expect(useDashboardLayoutStore.getState().cardOrder).toEqual(next);
  });

  it("toggleCardVisibility hides and re-shows a card", () => {
    useDashboardLayoutStore.getState().toggleCardVisibility("recent-activity");
    expect(useDashboardLayoutStore.getState().hiddenCards).toContain("recent-activity");

    useDashboardLayoutStore.getState().toggleCardVisibility("recent-activity");
    expect(useDashboardLayoutStore.getState().hiddenCards).not.toContain("recent-activity");
  });

  it("cycleCardSize cycles sm -> md -> lg -> sm", () => {
    useDashboardLayoutStore.setState({ cardSizes: { ...useDashboardLayoutStore.getState().cardSizes, user: "sm" } });

    useDashboardLayoutStore.getState().cycleCardSize("user");
    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("md");

    useDashboardLayoutStore.getState().cycleCardSize("user");
    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("lg");

    useDashboardLayoutStore.getState().cycleCardSize("user");
    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("sm");
  });

  it("resetLayout restores the default order, empties hidden cards, and resets sizes", () => {
    useDashboardLayoutStore.getState().moveCardUp(useDashboardLayoutStore.getState().cardOrder[1]!);
    useDashboardLayoutStore.getState().toggleCardVisibility("recent-activity");
    useDashboardLayoutStore.getState().cycleCardSize("user");

    useDashboardLayoutStore.getState().resetLayout();

    expect(useDashboardLayoutStore.getState().cardOrder).toEqual(DEFAULT_CARD_ORDER);
    expect(useDashboardLayoutStore.getState().hiddenCards).toEqual([]);
    expect(useDashboardLayoutStore.getState().cardSizes.user).toBe("sm");
  });

  it("toggleCustomizing flips isCustomizing", () => {
    expect(useDashboardLayoutStore.getState().isCustomizing).toBe(false);
    useDashboardLayoutStore.getState().toggleCustomizing();
    expect(useDashboardLayoutStore.getState().isCustomizing).toBe(true);
  });

  it("applyLayout replaces order/hidden/sizes wholesale", () => {
    useDashboardLayoutStore.getState().applyLayout({
      cardOrder: ["health-panel", "user"],
      hiddenCards: ["connectivity"],
      cardSizes: { ...useDashboardLayoutStore.getState().cardSizes, "health-panel": "lg" },
    });

    expect(useDashboardLayoutStore.getState().cardOrder).toEqual(["health-panel", "user"]);
    expect(useDashboardLayoutStore.getState().hiddenCards).toEqual(["connectivity"]);
    expect(useDashboardLayoutStore.getState().cardSizes["health-panel"]).toBe("lg");
  });
});
