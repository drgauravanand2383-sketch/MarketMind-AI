import { useState, type ReactNode } from "react";
import { SettingsField } from "@/features/settings/settings-field";
import { usePreferencesStore } from "@/store/preferences-store";
import type { NotificationDomain } from "@/store/realtime-notification-store";

const TOAST_DURATION_OPTIONS = [3_000, 6_000, 10_000, 15_000];

const DOMAIN_LABELS: Record<NotificationDomain, string> = {
  alerts: "Alerts",
  backtests: "Backtests",
  recommendations: "Recommendations",
  strategy: "Strategy",
  explainability: "Explainability",
  health: "Health",
  market: "Market",
  news: "News",
  decisions: "Decisions",
};
const ALL_DOMAINS = Object.keys(DOMAIN_LABELS) as NotificationDomain[];

function desktopPermission(): NotificationPermission | "unsupported" {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission;
}

export function NotificationsTab(): ReactNode {
  const notifications = usePreferencesStore((state) => state.notifications);
  const setToastDurationMs = usePreferencesStore((state) => state.setToastDurationMs);
  const setDefaultPinned = usePreferencesStore((state) => state.setDefaultPinned);
  const setSoundEnabled = usePreferencesStore((state) => state.setSoundEnabled);
  const setDesktopNotificationsEnabled = usePreferencesStore((state) => state.setDesktopNotificationsEnabled);
  const toggleNotificationCategory = usePreferencesStore((state) => state.toggleNotificationCategory);
  const resetSection = usePreferencesStore((state) => state.resetSection);

  const [permission, setPermission] = useState(desktopPermission());

  async function handleDesktopToggle(checked: boolean): Promise<void> {
    if (!checked) {
      setDesktopNotificationsEnabled(false);
      return;
    }
    if (typeof Notification === "undefined") {
      setDesktopNotificationsEnabled(false);
      return;
    }
    const result = permission === "default" ? await Notification.requestPermission() : permission;
    setPermission(result);
    setDesktopNotificationsEnabled(result === "granted");
  }

  return (
    <div className="flex flex-col">
      <SettingsField label="Toast duration">
        <label className="sr-only" htmlFor="toast-duration">
          Toast duration
        </label>
        <select
          id="toast-duration"
          value={notifications.toastDurationMs}
          onChange={(event) => {
            setToastDurationMs(Number(event.target.value));
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {TOAST_DURATION_OPTIONS.map((ms) => (
            <option key={ms} value={ms}>
              {(ms / 1000).toFixed(0)}s
            </option>
          ))}
        </select>
      </SettingsField>

      <SettingsField label="Pin new toasts by default" description="Pinned toasts never auto-dismiss.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={notifications.defaultPinned}
            onChange={(event) => {
              setDefaultPinned(event.target.checked);
            }}
          />
          Pinned
        </label>
      </SettingsField>

      <SettingsField label="Sound" description="UI preference only — no audio plays yet.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={notifications.soundEnabled}
            onChange={(event) => {
              setSoundEnabled(event.target.checked);
            }}
          />
          Sound on
        </label>
      </SettingsField>

      <SettingsField
        label="Desktop notifications"
        description={
          permission === "unsupported"
            ? "Not supported in this browser."
            : permission === "denied"
              ? "Blocked in your browser's site settings — enable it there first."
              : "Requests browser permission the first time you turn this on."
        }
      >
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={notifications.desktopNotificationsEnabled}
            disabled={permission === "unsupported" || permission === "denied"}
            onChange={(event) => {
              void handleDesktopToggle(event.target.checked);
            }}
          />
          Enabled
        </label>
      </SettingsField>

      <SettingsField label="Notification categories" description="Which domains generate toasts and Notification Center entries.">
        <div role="group" aria-label="Notification categories" className="flex flex-wrap gap-2">
          {ALL_DOMAINS.map((domain) => (
            <label key={domain} className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={notifications.enabledCategories.includes(domain)}
                onChange={() => {
                  toggleNotificationCategory(domain);
                }}
              />
              {DOMAIN_LABELS[domain]}
            </label>
          ))}
        </div>
      </SettingsField>

      <div className="pt-3">
        <button
          type="button"
          onClick={() => {
            resetSection("notifications");
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Reset notifications
        </button>
      </div>
    </div>
  );
}
