import type { ReactNode } from "react";
import { Panel } from "@/components/panel";
import { useCurrentUser } from "@/hooks/use-auth";
import { useVersion } from "@/hooks/use-health";
import { formatDateTime } from "@/lib/formatting";
import { API_BASE_URL, WS_BASE_URL } from "@/services/api/config";
import { useAuthStore } from "@/store/auth-store";
import { usePreferencesStore } from "@/store/preferences-store";

function initials(displayName: string | null, username: string): string {
  return (displayName ?? username).slice(0, 2).toUpperCase();
}

function InfoRow({ label, value }: { label: string; value: ReactNode }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  );
}

/**
 * Read-only account/session/API information — Milestone 8 "User
 * Profile." Never displays a raw token value (`AccessToken.token`/
 * `RefreshToken.token`), only their metadata (issued/expires
 * timestamps) — showing the actual secret on screen would be a real
 * security regression for a "read-only summary" page.
 */
export function ProfilePage(): ReactNode {
  const user = useCurrentUser();
  const accessToken = useAuthStore((state) => state.accessToken);
  const refreshToken = useAuthStore((state) => state.refreshToken);
  const version = useVersion();
  const timezoneDisplay = usePreferencesStore((state) => state.appearance.timezoneDisplay);
  const numberFormatLocale = usePreferencesStore((state) => state.appearance.numberFormatLocale);

  if (!user) return null;

  const formatTime = (iso: string): string => formatDateTime(iso, timezoneDisplay, numberFormatLocale);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-4">
        <span
          aria-hidden="true"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-xl font-semibold text-white"
        >
          {initials(user.display_name, user.username)}
        </span>
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{user.display_name ?? user.username}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{user.email}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Account summary">
          <dl>
            <InfoRow label="Status" value={user.status} />
            <InfoRow label="Roles" value={user.roles.length > 0 ? user.roles.join(", ") : "—"} />
            <InfoRow label="Permissions" value={`${String(user.permissions.length)} granted`} />
          </dl>
        </Panel>

        <Panel title="User information">
          <dl>
            <InfoRow label="Username" value={user.username} />
            <InfoRow label="Email" value={user.email} />
            <InfoRow label="Account created" value={formatTime(user.created_at)} />
            <InfoRow label="Last updated" value={formatTime(user.updated_at)} />
          </dl>
        </Panel>

        <Panel title="Session information">
          <dl>
            <InfoRow label="Access token issued" value={accessToken ? formatTime(accessToken.issued_at) : "—"} />
            <InfoRow label="Access token expires" value={accessToken ? formatTime(accessToken.expires_at) : "—"} />
            <InfoRow label="Refresh token issued" value={refreshToken ? formatTime(refreshToken.issued_at) : "—"} />
            <InfoRow label="Refresh token expires" value={refreshToken ? formatTime(refreshToken.expires_at) : "—"} />
          </dl>
        </Panel>

        <Panel title="Connected API">
          <dl>
            <InfoRow label="API base URL" value={API_BASE_URL} />
            <InfoRow label="WebSocket URL" value={WS_BASE_URL} />
            <InfoRow label="API version" value={version.data?.api_version ?? "—"} />
            <InfoRow label="Application version" value={version.data?.application_version ?? "—"} />
            <InfoRow label="Environment" value={version.data?.environment ?? "—"} />
          </dl>
        </Panel>
      </div>
    </div>
  );
}
