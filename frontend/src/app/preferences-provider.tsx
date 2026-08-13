import { useEffect, type ReactNode } from "react";
import { MotionConfig } from "framer-motion";
import { usePreferencesStore } from "@/store/preferences-store";

/**
 * Applies Milestone 8's Appearance/Accessibility preferences globally:
 * - `reducedMotion` wraps the whole tree in Framer Motion's own
 *   `MotionConfig` (already a project dependency — no new one added),
 *   which every existing `motion.*`/`AnimatePresence` usage (`Dialog`,
 *   `NotificationCenter`, `Sidebar`'s mobile drawer, `ConfirmDialog`,
 *   etc.) already respects automatically, with zero changes to any of
 *   those components.
 * - `density`/`highContrast`/`largeText`/`focusHighlight` toggle classes
 *   on `<html>` that `src/styles/globals.css` defines, the same
 *   `documentElement.classList` pattern `theme-store.ts`'s `applyTheme`
 *   already established for dark mode.
 */
export function PreferencesProvider({ children }: { children: ReactNode }): ReactNode {
  const accessibility = usePreferencesStore((state) => state.accessibility);
  const density = usePreferencesStore((state) => state.appearance.density);

  useEffect(() => {
    document.documentElement.classList.toggle("compact", density === "compact");
  }, [density]);

  useEffect(() => {
    document.documentElement.classList.toggle("high-contrast", accessibility.highContrast);
  }, [accessibility.highContrast]);

  useEffect(() => {
    document.documentElement.classList.toggle("large-text", accessibility.largeText);
  }, [accessibility.largeText]);

  useEffect(() => {
    document.documentElement.classList.toggle("focus-highlight", accessibility.focusHighlight);
  }, [accessibility.focusHighlight]);

  return <MotionConfig reducedMotion={accessibility.reducedMotion ? "always" : "never"}>{children}</MotionConfig>;
}
