import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useNotificationStore, type Notification, type NotificationType } from "@/store/notification-store";

const TYPE_STYLES: Record<NotificationType, string> = {
  success: "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950 dark:text-green-200",
  info: "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200",
  warning: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
  error: "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
};

const TYPE_ICONS: Record<NotificationType, string> = {
  success: "✓",
  info: "ℹ",
  warning: "⚠",
  error: "✕",
};

function Toast({ notification }: { notification: Notification }): ReactNode {
  const dismiss = useNotificationStore((state) => state.dismiss);
  const isAssertive = notification.type === "error" || notification.type === "warning";

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: -12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 32 }}
      transition={{ duration: 0.18 }}
      role={isAssertive ? "alert" : "status"}
      aria-live={isAssertive ? "assertive" : "polite"}
      className={`pointer-events-auto flex w-80 max-w-[calc(100vw-2rem)] items-start gap-3 rounded-lg border p-3 shadow-lg ${TYPE_STYLES[notification.type]}`}
    >
      <span aria-hidden="true" className="mt-0.5 text-sm font-bold">
        {TYPE_ICONS[notification.type]}
      </span>
      <div className="min-w-0 flex-1">
        {notification.title && <p className="text-sm font-semibold">{notification.title}</p>}
        <p className="text-sm">{notification.message}</p>
      </div>
      <button
        type="button"
        onClick={() => {
          dismiss(notification.id);
        }}
        aria-label="Dismiss notification"
        className="shrink-0 rounded p-0.5 text-current/70 hover:text-current"
      >
        ✕
      </button>
    </motion.li>
  );
}

export function NotificationCenter(): ReactNode {
  const notifications = useNotificationStore((state) => state.notifications);

  return (
    <ul className="pointer-events-none fixed right-4 top-4 z-50 flex flex-col gap-2">
      <AnimatePresence initial={false}>
        {notifications.map((notification) => (
          <Toast key={notification.id} notification={notification} />
        ))}
      </AnimatePresence>
    </ul>
  );
}
