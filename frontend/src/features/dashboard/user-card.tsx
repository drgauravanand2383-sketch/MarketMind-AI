import type { ReactNode } from "react";
import { useCurrentUser } from "@/hooks/use-auth";

export function UserCard(): ReactNode {
  const user = useCurrentUser();

  if (!user) return null;

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <p className="text-xs text-slate-500 dark:text-slate-400">Signed in as</p>
      <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{user.display_name ?? user.username}</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
        <dt>Username</dt>
        <dd className="text-slate-700 dark:text-slate-300">{user.username}</dd>
        <dt>Email</dt>
        <dd className="text-slate-700 dark:text-slate-300">{user.email}</dd>
        <dt>Roles</dt>
        <dd className="text-slate-700 dark:text-slate-300">{user.roles.length > 0 ? user.roles.join(", ") : "—"}</dd>
      </dl>
    </div>
  );
}
