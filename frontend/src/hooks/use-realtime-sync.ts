import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWebSocket } from "@/hooks/use-websocket";
import { useRealtimeSubscriptions } from "@/hooks/use-realtime-subscriptions";
import { invalidateForEvent } from "@/lib/realtime-invalidation";
import { toNotificationEntry } from "@/lib/realtime-notifications";
import { notify, type NotificationType } from "@/store/notification-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";
import type { DomainEvent } from "@/types/websocket";

/** Fires a real, permission-aware desktop notification — a no-op unless
 * the user both enabled it (`preferences-store.ts`'s `notifications
 * .desktopNotificationsEnabled`, set only after the browser actually
 * granted permission — see `features/settings/tabs/notifications-tab.tsx`)
 * and the browser still reports `"granted"` at the moment the event
 * arrives (permission can be revoked at any time from outside the app). */
function fireDesktopNotification(title: string, body: string): void {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification(title, { body });
}

function toastFor(event: DomainEvent): { type: NotificationType; message: string; pinned?: boolean } | null {
  switch (event.event_type) {
    case "ALERT_GENERATED": {
      const critical = event.payload.priority === "CRITICAL";
      const type: NotificationType = critical ? "error" : event.payload.priority === "HIGH" ? "warning" : "info";
      return { type, message: `New ${event.payload.priority} alert — ${event.payload.ticker}.`, pinned: critical };
    }
    case "BACKTEST_STARTED":
      return { type: "info", message: "Backtest started." };
    case "BACKTEST_COMPLETED":
      return { type: "success", message: "Backtest completed." };
    case "RECOMMENDATION_GENERATED":
      return { type: "success", message: `${String(event.payload.total_candidates)} recommendations generated.` };
    case "STRATEGY_EVALUATION_COMPLETED":
      return { type: "success", message: "Strategy evaluation completed." };
    case "EXPLAINABILITY_COMPLETED":
      return { type: "success", message: "Explainability report generated." };
    case "HEALTH_STATUS_CHANGED":
      return {
        type: event.payload.state === "HEALTHY" ? "success" : event.payload.state === "DEGRADED" ? "warning" : "error",
        message: `System health changed to ${event.payload.state}.`,
      };
    case "RISK_ASSESSMENT_COMPLETED":
      return null; // never actually published — see types/websocket.ts
    case "MARKET_SNAPSHOT_REFRESHED":
    case "PORTFOLIO_INTELLIGENCE_UPDATED":
      return null; // a fetch/refresh completing, not a proactive notice — see lib/realtime-notifications.ts
    case "SIGNIFICANT_MARKET_CHANGE":
    case "SIGNIFICANT_NEWS_UPDATE":
    case "PORTFOLIO_INTELLIGENCE_CHANGED": {
      const critical = event.payload.priority === "CRITICAL";
      const type: NotificationType = critical ? "error" : event.payload.priority === "HIGH" ? "warning" : "info";
      return { type, message: event.payload.summary, pinned: critical };
    }
  }
}

/**
 * The single real-time dispatch point for the whole app — mounted
 * exactly once, in `AppShell`. Owns the app's one `useWebSocket()` call
 * (see that hook's docstring for why a second caller would be a bug);
 * every inbound event fans out to three places: TanStack Query cache
 * invalidation (`invalidateForEvent`), the persistent Notification
 * Center (`realtime-notification-store`), and a toast
 * (`notification-store`'s existing `notify()`). Connection state is
 * mirrored into `realtime-connection-store` so read-only consumers
 * (`ConnectivityPanel`, the notification bell) never need their own
 * `useWebSocket()` call.
 */
export function useRealtimeSync(): void {
  const queryClient = useQueryClient();
  const subscriptions = useRealtimeSubscriptions();
  const ws = useWebSocket(subscriptions);
  const previousState = useRef(ws.state);

  useEffect(() => {
    useRealtimeConnectionStore.setState({
      state: ws.state,
      lastEventAt: ws.lastEventAt,
      lastHeartbeatAt: ws.lastHeartbeatAt,
      reconnect: ws.reconnect,
    });

    if (ws.state === "failed" && previousState.current !== "failed") {
      notify("error", "Real-time connection failed after multiple attempts. Reconnect manually to resume live updates.", {
        pinned: true,
      });
    }
    previousState.current = ws.state;
  }, [ws.state, ws.lastEventAt, ws.lastHeartbeatAt, ws.reconnect]);

  useEffect(() => {
    if (ws.lastMessage?.type !== "event") return;
    const { event } = ws.lastMessage;

    invalidateForEvent(queryClient, event);

    const entry = toNotificationEntry(event);
    if (!entry) return; // RISK_ASSESSMENT_COMPLETED — never actually published, see types/websocket.ts

    // Cache invalidation above always runs (a data-freshness concern);
    // the Notification Center entry, toast, and desktop notification are
    // all gated by the user's own category preference.
    const { enabledCategories, desktopNotificationsEnabled } = usePreferencesStore.getState().notifications;
    if (!enabledCategories.includes(entry.domain)) return;

    useRealtimeNotificationStore.getState().addEntry(entry);

    const toast = toastFor(event);
    if (toast) {
      notify(toast.type, toast.message, { ...(toast.pinned !== undefined && { pinned: toast.pinned }) });
    }

    if (desktopNotificationsEnabled) {
      fireDesktopNotification(entry.title, entry.summary);
    }
  }, [ws.lastMessage, queryClient]);
}
