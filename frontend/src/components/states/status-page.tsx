import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

export interface StatusPageProps {
  code: string;
  title: string;
  description: string;
  action: { label: string; to: string; search?: Record<string, string> };
}

/** Full-page status interstitial — 404, 401 ("unauthorized"), 403
 * ("forbidden"), and the root error boundary all share this shape (a
 * code, a title, an explanation, one way forward), so it's one
 * component parameterized by copy rather than four near-identical pages. */
export function StatusPage({ code, title, description, action }: StatusPageProps): ReactNode {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm font-semibold text-brand-600 dark:text-brand-400">{code}</p>
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{title}</h1>
      <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">{description}</p>
      <Link
        to={action.to}
        {...(action.search !== undefined && { search: action.search })}
        className="mt-2 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
      >
        {action.label}
      </Link>
    </div>
  );
}
