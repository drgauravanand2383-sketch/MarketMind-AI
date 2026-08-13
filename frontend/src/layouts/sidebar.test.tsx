import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { Sidebar } from "@/layouts/sidebar";
import { useAuthStore } from "@/store/auth-store";
import { useUiStore } from "@/store/ui-store";
import { testUser } from "@/test/msw/fixtures";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ to, children, onClick }: { to: string; children?: ReactNode; onClick?: () => void }) => (
      <a href={to} onClick={onClick}>
        {children}
      </a>
    ),
  };
});

describe("Sidebar", () => {
  beforeEach(() => {
    useUiStore.setState({ sidebarCollapsed: false, mobileNavOpen: false });
    useAuthStore.setState({ status: "authenticated", user: { ...testUser, permissions: ["watchlist:read"] } });
  });

  it("only lists domains the signed-in user has permission to view, plus Dashboard", () => {
    render(<Sidebar />);

    expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Watchlists").length).toBeGreaterThan(0);
    expect(screen.queryByText("Backtesting")).not.toBeInTheDocument();
  });

  it("the mobile drawer is closed by default and opens when mobileNavOpen becomes true", () => {
    const { rerender } = render(<Sidebar />);
    expect(screen.queryByRole("dialog", { name: "Primary navigation" })).not.toBeInTheDocument();

    useUiStore.setState({ mobileNavOpen: true });
    rerender(<Sidebar />);

    expect(screen.getByRole("dialog", { name: "Primary navigation" })).toBeInTheDocument();
  });

  it("closes the mobile drawer when Escape is pressed", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ mobileNavOpen: true });
    render(<Sidebar />);
    expect(screen.getByRole("dialog", { name: "Primary navigation" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(useUiStore.getState().mobileNavOpen).toBe(false);
  });

  it("closes the mobile drawer when a nav link inside it is clicked", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ mobileNavOpen: true });
    render(<Sidebar />);

    const dialog = screen.getByRole("dialog", { name: "Primary navigation" });
    await user.click(within(dialog).getByText("Dashboard"));

    expect(useUiStore.getState().mobileNavOpen).toBe(false);
  });

  it("moves initial focus into the drawer and traps Tab within it", async () => {
    const user = userEvent.setup();
    useUiStore.setState({ mobileNavOpen: true });
    render(<Sidebar />);

    const dialog = screen.getByRole("dialog", { name: "Primary navigation" });
    const focusable = within(dialog).getAllByRole("link").concat(within(dialog).getByRole("button", { name: "Close navigation" }));
    const closeButton = within(dialog).getByRole("button", { name: "Close navigation" });
    const links = within(dialog).getAllByRole("link");
    const lastLink = links[links.length - 1];

    expect(closeButton).toHaveFocus();

    await user.tab({ shift: true });
    expect(lastLink).toHaveFocus();

    await user.tab();
    expect(closeButton).toHaveFocus();

    expect(focusable.length).toBeGreaterThan(1);
  });
});
