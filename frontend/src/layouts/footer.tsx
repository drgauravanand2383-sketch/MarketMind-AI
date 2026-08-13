import type { ReactNode } from "react";
import { useVersion } from "@/hooks/use-health";

export function Footer(): ReactNode {
  const { data: version } = useVersion();

  return (
    <footer className="flex h-10 items-center justify-between border-t border-slate-200 px-4 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
      <span>MarketMind AI</span>
      <span>
        {version ? `v${version.application_version} · ${version.environment}` : "—"}
      </span>
    </footer>
  );
}
