import { useState, type ReactNode } from "react";
import { Button } from "@/components/button";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { usePreferencesStore } from "@/store/preferences-store";

export function ResetAllButton(): ReactNode {
  const [open, setOpen] = useState(false);
  const resetAll = usePreferencesStore((state) => state.resetAll);
  const resetLayout = useDashboardLayoutStore((state) => state.resetLayout);

  return (
    <>
      <Button
        variant="destructive-outline"
        onClick={() => {
          setOpen(true);
        }}
      >
        Reset all preferences
      </Button>
      <ConfirmDialog
        open={open}
        title="Reset all preferences?"
        message="This resets every appearance, table, chart, notification, accessibility, and dashboard layout preference to its default. Saved views are kept."
        confirmLabel="Reset all"
        destructive
        onConfirm={() => {
          resetAll();
          resetLayout();
          setOpen(false);
        }}
        onCancel={() => {
          setOpen(false);
        }}
      />
    </>
  );
}
