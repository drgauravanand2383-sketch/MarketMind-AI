import { beforeEach, describe, expect, it } from "vitest";
import { useShortcutsStore } from "@/store/shortcuts-store";

function resetShortcutsStore(): void {
  useShortcutsStore.persist.clearStorage();
  useShortcutsStore.setState({ helpOpen: false, bindings: useShortcutsStore.getInitialState().bindings });
}

describe("shortcuts-store", () => {
  beforeEach(() => {
    resetShortcutsStore();
  });

  it("defaults every action to its documented default key", () => {
    expect(useShortcutsStore.getState().bindings.search).toBe("/");
    expect(useShortcutsStore.getState().bindings.help).toBe("?");
    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
  });

  it("setBinding rebinds one action without touching the others", () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("x");
    expect(useShortcutsStore.getState().bindings.goToWatchlists).toBe("w");
  });

  it("resetBinding restores just that one action's default", () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");
    useShortcutsStore.getState().setBinding("goToWatchlists", "y");

    useShortcutsStore.getState().resetBinding("goToDashboard");

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
    expect(useShortcutsStore.getState().bindings.goToWatchlists).toBe("y");
  });

  it("resetAll restores every binding to its default", () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");
    useShortcutsStore.getState().setBinding("search", "y");

    useShortcutsStore.getState().resetAll();

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
    expect(useShortcutsStore.getState().bindings.search).toBe("/");
  });

  it("persists bindings, but not helpOpen, to localStorage", () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");
    useShortcutsStore.getState().openHelp();

    const raw = window.localStorage.getItem("marketmind-shortcuts");
    expect(raw).toContain("\"goToDashboard\":\"x\"");
    expect(raw).not.toContain("helpOpen");
  });

  it("openHelp/closeHelp toggle the transient helpOpen flag", () => {
    useShortcutsStore.getState().openHelp();
    expect(useShortcutsStore.getState().helpOpen).toBe(true);

    useShortcutsStore.getState().closeHelp();
    expect(useShortcutsStore.getState().helpOpen).toBe(false);
  });
});
