import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { PriorityBadge } from "@/components/priority-badge";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";

const PREVIEW_COUNT = 8;

/**
 * Mirrors `UserMenu`'s open/close mechanics (pointerdown-outside +
 * Escape to close) but deliberately does **not** use `role="menu"`/
 * `role="menuitem"` — entries here are read/navigate targets, not
 * commands, so the ARIA menu pattern (which implies roving-tabindex
 * arrow-key navigation) would be the wrong semantics. The panel is a
 * plain labeled region containing normal focusable links/buttons.
 */
export function NotificationBell(): ReactNode {
  // Selecting the stable `entries` array and deriving the unread count
  // in the component body (never inside the selector) — see
  // `realtime-notification-store.ts`'s docstring on the M6
  // `useSyncExternalStore` infinite-loop footgun this avoids.
  const entries = useRealtimeNotificationStore((state) => state.entries);
  const markRead = useRealtimeNotificationStore((state) => state.markRead);
  const markAllRead = useRealtimeNotificationStore((state) => state.markAllRead);
  const unreadCount = entries.filter((entry) => !entry.read).length;
  const preview = entries.slice(0, PREVIEW_COUNT);

  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent): void {
      const target = event.target as Node;
      if (!panelRef.current?.contains(target) && !buttonRef.current?.contains(target)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="relative">
      <span aria-live="polite" className="sr-only">
        {unreadCount > 0 ? `${String(unreadCount)} unread notification${unreadCount === 1 ? "" : "s"}` : ""}
      </span>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          setOpen((value) => !value);
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={unreadCount > 0 ? `Notifications (${String(unreadCount)} unread)` : "Notifications"}
        className="relative rounded-md p-2.5 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        <span aria-hidden="true">🔔</span>
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          aria-label="Notifications"
          className="absolute right-0 z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-md border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex items-center justify-between px-1 py-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Notifications</span>
            <button
              type="button"
              onClick={markAllRead}
              className="text-xs font-medium text-brand-700 hover:underline dark:text-brand-400"
            >
              Mark all read
            </button>
          </div>

          {preview.length === 0 ? (
            <p className="px-1 py-3 text-sm text-slate-500 dark:text-slate-400">No notifications yet this session.</p>
          ) : (
            <ul className="mt-1 flex max-h-96 flex-col gap-1 overflow-y-auto">
              {preview.map((entry) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => {
                      markRead(entry.id);
                    }}
                    className="flex w-full flex-col items-start gap-0.5 rounded-md p-2 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                  >
                    <span className="flex items-center gap-1.5">
                      {!entry.read && <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-600" />}
                      {entry.priority && <PriorityBadge level={entry.priority} />}
                      <span className={`text-sm ${entry.read ? "text-slate-600 dark:text-slate-400" : "font-medium text-slate-900 dark:text-slate-100"}`}>
                        {entry.title}
                      </span>
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">{new Date(entry.occurredAt).toLocaleString()}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-1 border-t border-slate-100 pt-1 dark:border-slate-800">
            <Link
              to="/notifications"
              onClick={() => {
                setOpen(false);
              }}
              className="block rounded-md px-2 py-1.5 text-center text-sm font-medium text-brand-700 hover:bg-slate-100 dark:text-brand-400 dark:hover:bg-slate-800"
            >
              View all
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
