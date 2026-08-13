import type { ReactNode } from "react";
import { Button } from "@/components/button";
import { Dialog } from "@/components/dialog";
import { LoadingButton } from "@/components/forms/loading-button";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  isLoading?: boolean;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  isLoading = false,
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps): ReactNode {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <LoadingButton
            type="button"
            onClick={onConfirm}
            isLoading={isLoading}
            className={
              destructive
                ? "inline-flex items-center justify-center gap-2 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                : undefined
            }
          >
            {confirmLabel}
          </LoadingButton>
        </>
      }
    >
      <p className="text-sm text-slate-600 dark:text-slate-300">{message}</p>
    </Dialog>
  );
}
