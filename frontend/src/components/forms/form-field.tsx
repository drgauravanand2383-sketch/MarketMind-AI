import { forwardRef, useId, type InputHTMLAttributes } from "react";

export interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | undefined;
}

/** A labeled input with wired-up accessibility: the label's `htmlFor`
 * always matches the input's `id` (generated via `useId` if the caller
 * doesn't supply one), and an inline error is linked back to the input
 * via `aria-describedby`/`aria-invalid` — a screen reader announces it
 * the same way a sighted user sees it, not just as red text. Forwards
 * its ref and spreads the rest of its props onto the native `<input>`,
 * so it drops directly into `{...register("field")}`. */
export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(function FormField(
  { label, error, id, className, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={
          className ??
          "rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        }
        {...props}
      />
      {error && (
        <p id={errorId} role="alert" className="text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
});
