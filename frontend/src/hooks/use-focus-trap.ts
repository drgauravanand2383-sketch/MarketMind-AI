import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Shared focus-trap behavior for any `role="dialog" aria-modal="true"`
 * region — moves focus into `containerRef`'s subtree (first focusable
 * element) when `active` becomes true, restores it to whatever was
 * focused before on deactivation, and returns an `onKeyDown` handler
 * that cycles Tab/Shift+Tab within the container instead of letting
 * focus escape into the page behind it.
 *
 * Extracted from `Dialog`'s own original implementation (Milestone 3) —
 * `Sidebar`'s mobile nav drawer (Milestone 2) declared `aria-modal="true"`
 * without ever actually trapping Tab, a real accessibility gap found in
 * the Milestone 9 audit; both now share this one implementation instead
 * of the drawer growing its own second copy.
 */
export function useFocusTrap(containerRef: RefObject<HTMLElement | null>, active: boolean): (event: ReactKeyboardEvent) => void {
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (active) {
      previouslyFocused.current = document.activeElement as HTMLElement | null;
      const firstFocusable = containerRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      firstFocusable?.focus();
    } else {
      previouslyFocused.current?.focus();
    }
  }, [active, containerRef]);

  return function handleTabTrap(event: ReactKeyboardEvent): void {
    if (event.key !== "Tab" || !containerRef.current) return;
    const focusable = Array.from(containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
}
