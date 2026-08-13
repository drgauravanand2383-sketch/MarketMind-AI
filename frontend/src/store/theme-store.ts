import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Resolves `mode` to an actual light/dark value, following the OS
 * setting when `mode === "system"`. */
export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode === "system") {
    return systemPrefersDark() ? "dark" : "light";
  }
  return mode;
}

/** Applies the resolved theme to `<html>` — Tailwind's `dark:` variant
 * is driven by the `.dark` class (see `src/styles/globals.css`'s
 * `@custom-variant dark`), not `prefers-color-scheme` directly, so
 * "system" mode still needs this applied once up front and again on
 * every OS-level change. */
export function applyTheme(mode: ThemeMode): void {
  const resolved = resolveTheme(mode);
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: "system",
      setMode: (mode) => {
        set({ mode });
        applyTheme(mode);
      },
    }),
    { name: "marketmind-theme" },
  ),
);
