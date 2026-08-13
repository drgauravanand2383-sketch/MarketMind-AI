import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShortcutsTab } from "@/features/settings/tabs/shortcuts-tab";
import { useShortcutsStore } from "@/store/shortcuts-store";

describe("ShortcutsTab", () => {
  beforeEach(() => {
    useShortcutsStore.persist.clearStorage();
    useShortcutsStore.setState({ helpOpen: false, bindings: useShortcutsStore.getInitialState().bindings });
  });

  it("lists every shortcut with its current key", () => {
    render(<ShortcutsTab />);

    expect(screen.getByText("Go to Dashboard")).toBeInTheDocument();
    expect(screen.getAllByText("d").length).toBeGreaterThan(0);
  });

  it("rebinds a shortcut by pressing a key after clicking Change", async () => {
    const user = userEvent.setup();
    render(<ShortcutsTab />);

    await user.click(screen.getAllByRole("button", { name: "Change" })[2]!);

    await user.keyboard("x");

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("x");
  });

  it("Escape cancels a capture without changing the binding", async () => {
    const user = userEvent.setup();
    render(<ShortcutsTab />);

    await user.click(screen.getAllByRole("button", { name: "Change" })[2]!);
    await user.keyboard("{Escape}");

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
  });

  it("Reset restores a single shortcut's default after it was changed", async () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");
    const user = userEvent.setup();
    render(<ShortcutsTab />);

    await user.click(screen.getAllByRole("button", { name: "Reset" })[2]!);

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
  });

  it("Reset all shortcuts restores every default", async () => {
    useShortcutsStore.getState().setBinding("goToDashboard", "x");
    useShortcutsStore.getState().setBinding("search", "y");
    const user = userEvent.setup();
    render(<ShortcutsTab />);

    await user.click(screen.getByRole("button", { name: "Reset all shortcuts" }));

    expect(useShortcutsStore.getState().bindings.goToDashboard).toBe("d");
    expect(useShortcutsStore.getState().bindings.search).toBe("/");
  });
});
