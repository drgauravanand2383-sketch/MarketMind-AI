import type { ReactNode } from "react";

const PALETTE = [
  "bg-blue-100 text-blue-800 dark:bg-blue-500/10 dark:text-blue-400",
  "bg-purple-100 text-purple-800 dark:bg-purple-500/10 dark:text-purple-400",
  "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  "bg-pink-100 text-pink-800 dark:bg-pink-500/10 dark:text-pink-400",
  "bg-teal-100 text-teal-800 dark:bg-teal-500/10 dark:text-teal-400",
  "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/10 dark:text-indigo-400",
  "bg-orange-100 text-orange-800 dark:bg-orange-500/10 dark:text-orange-400",
];

/** Sector/country/theme are free text on the backend (no fixed enum,
 * see `@/types/watchlist`), so there's no fixed color mapping to draw
 * from. A deterministic hash-to-palette-index gives every distinct
 * label a stable, consistent color across renders without hardcoding
 * a color per possible value. */
const NEUTRAL_CLASS = "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";

function hashToPaletteClass(label: string): string {
  let hash = 0;
  for (let index = 0; index < label.length; index += 1) {
    hash = (hash * 31 + label.charCodeAt(index)) | 0;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length] ?? NEUTRAL_CLASS;
}

export interface BadgeProps {
  label: string;
  /** "auto" (default) hashes `label` to a stable color; "neutral" for
   * badges with no inherent category color (e.g. a count). */
  tone?: "auto" | "neutral";
}

export function Badge({ label, tone = "auto" }: BadgeProps): ReactNode {
  const className = tone === "neutral" ? NEUTRAL_CLASS : hashToPaletteClass(label);
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>{label}</span>;
}
