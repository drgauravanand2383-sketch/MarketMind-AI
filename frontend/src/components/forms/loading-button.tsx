import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
  loadingText?: string;
}

const BASE_CLASSES =
  "inline-flex items-center justify-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50";

export function LoadingButton({
  isLoading = false,
  loadingText,
  children,
  disabled,
  className,
  type = "submit",
  ...props
}: LoadingButtonProps): ReactNode {
  return (
    <button type={type} disabled={disabled ?? isLoading} aria-busy={isLoading} className={className ?? BASE_CLASSES} {...props}>
      {isLoading && <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {isLoading ? (loadingText ?? children) : children}
    </button>
  );
}
