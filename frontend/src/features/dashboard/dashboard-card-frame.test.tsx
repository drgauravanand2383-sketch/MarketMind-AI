import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardCardFrame } from "@/features/dashboard/dashboard-card-frame";
import type { DashboardCardDefinition } from "@/features/dashboard/dashboard-card-registry";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";

function BrokenCard(): never {
  throw new Error("Boom");
}

describe("DashboardCardFrame", () => {
  beforeEach(() => {
    useDashboardLayoutStore.getState().resetLayout();
  });

  it("isolates a card that throws behind its own error boundary instead of crashing the whole page", () => {
    // React logs the caught error to the console by default — expected
    // here, not a real test failure signal.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const card: DashboardCardDefinition = { id: "user", label: "Account", panelTitle: "Account", render: () => <BrokenCard /> };

    render(<DashboardCardFrame card={card} isFirst isLast />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Account failed to load");
    expect(alert).toHaveTextContent("Boom");
    consoleError.mockRestore();
  });

  it("renders a working card's content normally, unaffected by the error boundary", () => {
    const card: DashboardCardDefinition = { id: "user", label: "Account", panelTitle: "Account", render: () => <p>All good</p> };

    render(<DashboardCardFrame card={card} isFirst isLast />);

    expect(screen.getByText("All good")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
