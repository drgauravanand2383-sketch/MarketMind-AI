import { useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";

interface RovingTablist {
  registerTabRef: (index: number) => (element: HTMLButtonElement | null) => void;
  handleTablistKeyDown: (event: ReactKeyboardEvent<HTMLDivElement>) => void;
}

/**
 * Shared ArrowLeft/ArrowRight/Home/End keyboard navigation for a
 * `role="tablist"` built from roving `tabIndex={isActive ? 0 : -1}`
 * buttons (the pattern `DecisionWorkspaceTabs` and
 * `WorkspaceSettingsPage` both already use). Without this, a tab with
 * `tabIndex={-1}` is unreachable by keyboard once focus leaves the
 * currently active tab — a Milestone 9 audit finding.
 *
 * Activation is immediate on arrow-key move (matching how these
 * tablists already activate immediately on click), so `onActivate` is
 * called and focus is moved to the newly-active tab button in one step.
 */
export function useRovingTablist<T extends string>(ids: readonly T[], activeId: T, onActivate: (id: T) => void): RovingTablist {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function registerTabRef(index: number): (element: HTMLButtonElement | null) => void {
    return (element: HTMLButtonElement | null) => {
      tabRefs.current[index] = element;
    };
  }

  function handleTablistKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const currentIndex = ids.indexOf(activeId);
    let nextIndex: number;
    switch (event.key) {
      case "ArrowRight":
        nextIndex = (currentIndex + 1) % ids.length;
        break;
      case "ArrowLeft":
        nextIndex = (currentIndex - 1 + ids.length) % ids.length;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = ids.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const nextId = ids[nextIndex];
    if (nextId === undefined) return;
    onActivate(nextId);
    tabRefs.current[nextIndex]?.focus();
  }

  return { registerTabRef, handleTablistKeyDown };
}
