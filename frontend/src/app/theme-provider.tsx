import { useEffect, type ReactNode } from "react";
import { applyTheme, useThemeStore } from "@/store/theme-store";

/** Applies the persisted theme to `<html>` on mount, and re-applies it
 * whenever the OS-level color scheme changes while `mode === "system"`.
 * Renders nothing itself — Tailwind's `dark:` variant does the rest. */
export function ThemeProvider({ children }: { children: ReactNode }): ReactNode {
  const mode = useThemeStore((state) => state.mode);

  useEffect(() => {
    applyTheme(mode);

    if (mode !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (): void => {
      applyTheme(mode);
    };
    media.addEventListener("change", handleChange);
    return () => {
      media.removeEventListener("change", handleChange);
    };
  }, [mode]);

  return children;
}
