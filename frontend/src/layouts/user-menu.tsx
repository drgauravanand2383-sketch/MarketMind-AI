import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useCurrentUser, useLogout } from "@/hooks/use-auth";
import type { User } from "@/types/auth";

function initials(user: User): string {
  const source = user.display_name ?? user.username;
  return source.slice(0, 2).toUpperCase();
}

/**
 * Mirrors `NotificationBell`'s pattern: a plain labeled region of
 * normal focusable links/buttons, not `role="menu"`/`role="menuitem"`
 * — the ARIA menu pattern implies roving-tabindex arrow-key/Home/End
 * navigation that neither component actually implements, so claiming
 * it would be misleading to assistive tech.
 */
export function UserMenu(): ReactNode {
  const user = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent): void {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) {
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

  if (!user) return null;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          setOpen((value) => !value);
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        <span
          aria-hidden="true"
          className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-semibold text-white"
        >
          {initials(user)}
        </span>
        <span className="hidden text-slate-700 sm:inline dark:text-slate-300">{user.display_name ?? user.username}</span>
      </button>

      {open && (
        <div
          ref={menuRef}
          aria-label="User menu"
          className="absolute right-0 z-30 mt-2 w-56 rounded-md border border-slate-200 bg-white p-2 shadow-lg dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="px-2 py-1.5 text-xs text-slate-500 dark:text-slate-400">
            Signed in as <span className="font-medium text-slate-700 dark:text-slate-300">{user.username}</span>
          </div>
          <Link
            to="/profile"
            onClick={() => {
              setOpen(false);
            }}
            className="block w-full rounded-md px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            View profile
          </Link>
          <Link
            to="/settings"
            onClick={() => {
              setOpen(false);
            }}
            className="block w-full rounded-md px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Workspace settings
          </Link>
          <div className="my-1 border-t border-slate-100 dark:border-slate-800" />
          <button
            type="button"
            onClick={() => {
              logout.mutate(undefined, {
                onSuccess: () => {
                  void navigate({ to: "/login" });
                },
              });
            }}
            disabled={logout.isPending}
            className="w-full rounded-md px-2 py-1.5 text-left text-sm text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950"
          >
            {logout.isPending ? "Logging out…" : "Log out"}
          </button>
        </div>
      )}
    </div>
  );
}
