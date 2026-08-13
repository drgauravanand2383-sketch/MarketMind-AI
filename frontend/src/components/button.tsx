import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "destructive" | "destructive-ghost" | "destructive-outline";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

// Two sizes, not the 4 distinct px/py/text combos an audit found spread
// across ~20 files with no apparent tiering (Milestone 9 finding) — `md`
// matches `LoadingButton`'s existing default exactly, so a `Button` and
// a `LoadingButton` placed side by side (e.g. `ConfirmDialog`'s footer)
// still line up.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3 py-2 text-sm",
};

// `destructive` (solid), `destructive-ghost`, and `destructive-outline`
// map to the 3 destructive tiers already in use by context (modal
// confirm-destroy, inline row-remove, one standalone dangerous action
// respectively) — an audit-confirmed *intentional* split, not drift, so
// all 3 are kept as distinct variants rather than collapsed into one.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700",
  secondary:
    "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800",
  destructive: "bg-red-600 text-white hover:bg-red-700",
  "destructive-ghost": "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950",
  "destructive-outline":
    "border border-red-300 text-red-800 hover:bg-red-100 dark:border-red-800 dark:text-red-200 dark:hover:bg-red-900",
};

const BASE_CLASSES = "inline-flex items-center justify-center gap-2 rounded-md font-medium disabled:cursor-not-allowed disabled:opacity-50";

/**
 * The shared button component this app never had (a Milestone 9 audit
 * finding — every button was one-off Tailwind strings, drifting to 4+
 * unrelated size combos for the same "primary" role). Deliberately not a
 * retrofit of every existing button in the app (~20+ files) — applied
 * here to new Milestone 9 code and to the most-drifted existing call
 * sites (`ConfirmDialog`, `ResetAllButton`); the rest is documented as
 * an accepted, out-of-scope gap in `docs/frontend/MILESTONE_9.md`.
 * `LoadingButton` (a distinct isLoading/spinner concern) is untouched.
 */
export function Button({ variant = "primary", size = "md", type = "button", className, ...rest }: ButtonProps): ReactNode {
  const classes = [BASE_CLASSES, SIZE_CLASSES[size], VARIANT_CLASSES[variant], className].filter(Boolean).join(" ");
  return <button type={type} className={classes} {...rest} />;
}
