import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeToggle } from "@/components/theme-toggle";
import { useThemeStore } from "@/store/theme-store";

describe("ThemeToggle", () => {
  beforeEach(() => {
    useThemeStore.setState({ mode: "system" });
    document.documentElement.classList.remove("dark");
  });

  it("switches to dark mode and applies the .dark class on <html>", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("radio", { name: "Dark" }));

    expect(useThemeStore.getState().mode).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("switches to light mode and removes the .dark class", async () => {
    const user = userEvent.setup();
    useThemeStore.setState({ mode: "dark" });
    document.documentElement.classList.add("dark");
    render(<ThemeToggle />);

    await user.click(screen.getByRole("radio", { name: "Light" }));

    expect(useThemeStore.getState().mode).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
