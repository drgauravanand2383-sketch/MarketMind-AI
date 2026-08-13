import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { useFocusTrap } from "@/hooks/use-focus-trap";
import { FEATURE_NAV_ITEMS } from "@/lib/nav-items";
import { useAuthStore } from "@/store/auth-store";
import { useUiStore } from "@/store/ui-store";

interface NavLinkSpec {
  to: string;
  label: string;
  icon: string;
}

function SidebarLink({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavLinkSpec;
  collapsed: boolean;
  onNavigate?: (() => void) | undefined;
}): ReactNode {
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      activeOptions={{ exact: item.to === "/" }}
      title={collapsed ? item.label : undefined}
      className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      activeProps={{
        "aria-current": "page",
        className: "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-400",
      }}
    >
      <span aria-hidden="true">{item.icon}</span>
      <span className={collapsed ? "sr-only" : ""}>{item.label}</span>
    </Link>
  );
}

// A stable, module-level reference — `state.user?.permissions ?? []`
// would allocate a fresh array on every selector call whenever `user`
// is null, which trips React's `useSyncExternalStore` "getSnapshot
// should be cached" infinite-loop detector.
const NO_PERMISSIONS: string[] = [];

function useVisibleFeatureItems(): NavLinkSpec[] {
  const permissions = useAuthStore((state) => state.user?.permissions ?? NO_PERMISSIONS);
  return FEATURE_NAV_ITEMS.filter((item) => permissions.includes(item.permission));
}

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: (() => void) | undefined }): ReactNode {
  const visibleItems = useVisibleFeatureItems();
  return (
    <nav aria-label="Primary" className="flex-1 overflow-y-auto p-4">
      <ul className="flex flex-col gap-1">
        <li>
          <SidebarLink item={{ to: "/", label: "Dashboard", icon: "🏠" }} collapsed={collapsed} onNavigate={onNavigate} />
        </li>
        <li>
          <SidebarLink item={{ to: "/notifications", label: "Notifications", icon: "🔔" }} collapsed={collapsed} onNavigate={onNavigate} />
        </li>
        {visibleItems.map((item) => (
          <li key={item.to}>
            <SidebarLink item={item} collapsed={collapsed} onNavigate={onNavigate} />
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function Sidebar(): ReactNode {
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const mobileNavOpen = useUiStore((state) => state.mobileNavOpen);
  const setMobileNavOpen = useUiStore((state) => state.setMobileNavOpen);
  const drawerRef = useRef<HTMLDivElement>(null);
  const handleTabTrap = useFocusTrap(drawerRef, mobileNavOpen);

  useEffect(() => {
    if (!mobileNavOpen) return;
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setMobileNavOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileNavOpen, setMobileNavOpen]);

  return (
    <>
      <aside
        className={`hidden shrink-0 flex-col border-r border-slate-200 bg-slate-50 transition-[width] duration-150 sm:flex dark:border-slate-800 dark:bg-slate-900 ${
          collapsed ? "w-16" : "w-56"
        }`}
      >
        <SidebarNav collapsed={collapsed} />
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="m-2 rounded-md p-2.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <span aria-hidden="true">{collapsed ? "»" : "«"}</span>
        </button>
      </aside>

      <AnimatePresence>
        {mobileNavOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => {
                setMobileNavOpen(false);
              }}
              aria-hidden="true"
              className="fixed inset-0 z-40 bg-black/40 sm:hidden"
            />
            <motion.div
              key="drawer"
              ref={drawerRef}
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.2 }}
              role="dialog"
              aria-modal="true"
              aria-label="Primary navigation"
              onKeyDown={handleTabTrap}
              className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-white shadow-xl sm:hidden dark:bg-slate-900"
            >
              <button
                type="button"
                onClick={() => {
                  setMobileNavOpen(false);
                }}
                aria-label="Close navigation"
                className="m-2 self-end rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <span aria-hidden="true">✕</span>
              </button>
              <SidebarNav
                collapsed={false}
                onNavigate={() => {
                  setMobileNavOpen(false);
                }}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
