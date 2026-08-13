import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useNetworkStatusStore } from "@/store/network-status-store";

describe("network-status-store", () => {
  const originalOnLine = window.navigator.onLine;

  beforeEach(() => {
    useNetworkStatusStore.setState({ online: true });
  });

  afterEach(() => {
    Object.defineProperty(window.navigator, "onLine", { value: originalOnLine, configurable: true });
  });

  it("flips to false when the browser fires 'offline'", () => {
    window.dispatchEvent(new Event("offline"));

    expect(useNetworkStatusStore.getState().online).toBe(false);
  });

  it("flips back to true when the browser fires 'online'", () => {
    useNetworkStatusStore.setState({ online: false });

    window.dispatchEvent(new Event("online"));

    expect(useNetworkStatusStore.getState().online).toBe(true);
  });
});
