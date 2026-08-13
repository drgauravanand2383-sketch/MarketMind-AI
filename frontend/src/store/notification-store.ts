import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";

export type NotificationType = "success" | "info" | "warning" | "error";

export interface Notification {
  id: string;
  type: NotificationType;
  message: string;
  title?: string;
}

export interface NotifyOptions {
  title?: string;
  durationMs?: number;
  /** Clearer-named alias for `durationMs: 0` ("never auto-dismiss") —
   * not a second, independent field. `pinned: true` simply forces the
   * zero-duration path; `Notification` itself needs no new stored field
   * for it (the toast UI never needs to know *why* nothing was
   * scheduled, only that nothing was). */
  pinned?: boolean;
}

interface NotificationState {
  notifications: Notification[];
  notify: (type: NotificationType, message: string, options?: NotifyOptions) => string;
  dismiss: (id: string) => void;
}

let nextId = 0;

/** Ephemeral by design — never persisted. A notification is a moment in
 * time ("your session expired"), not state worth restoring across a
 * page reload. */
export const useNotificationStore = create<NotificationState>()((set, get) => ({
  notifications: [],

  notify: (type, message, options) => {
    // Reuse an already-visible notification with the same message
    // instead of stacking duplicates — a health-check poll failing
    // every 15s shouldn't flood the toast stack with identical errors.
    const existing = get().notifications.find((n) => n.type === type && n.message === message);
    if (existing) {
      return existing.id;
    }

    nextId += 1;
    const id = `notification-${String(nextId)}`;
    const notification: Notification = { id, type, message, ...(options?.title !== undefined && { title: options.title }) };
    set((state) => ({ notifications: [...state.notifications, notification] }));

    // `options?.pinned`/`options?.durationMs` (an explicit, call-site
    // choice) always win; otherwise fall back to the user's own
    // Notification preferences (`preferences-store.ts`, Milestone 8).
    const notificationPreferences = usePreferencesStore.getState().notifications;
    const pinned = options?.pinned ?? notificationPreferences.defaultPinned;
    const durationMs = pinned ? 0 : (options?.durationMs ?? notificationPreferences.toastDurationMs);
    if (durationMs > 0) {
      setTimeout(() => {
        get().dismiss(id);
      }, durationMs);
    }
    return id;
  },

  dismiss: (id) => {
    set((state) => ({ notifications: state.notifications.filter((n) => n.id !== id) }));
  },
}));

/** Plain-function form for call sites outside a React render (the
 * `QueryClient`'s global error handlers, `ApiClient` consumers,
 * `auth-store`'s session-expiry path) — identical to calling the hook's
 * `notify`, just without needing a component. */
export function notify(type: NotificationType, message: string, options?: NotifyOptions): string {
  return useNotificationStore.getState().notify(type, message, options);
}
