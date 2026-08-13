import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { UserMenu } from "@/layouts/user-menu";
import { renderWithQueryClient } from "@/test/test-utils";
import { useAuthStore } from "@/store/auth-store";
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
    useNavigate: () => () => {},
  };
});

describe("UserMenu", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "authenticated", user: testUser });
  });

  it("renders nothing when there is no signed-in user", () => {
    useAuthStore.setState({ user: null });
    const { container } = renderWithQueryClient(<UserMenu />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not claim ARIA menu semantics — a plain labeled region of normal links/buttons instead", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<UserMenu />);

    await user.click(screen.getByRole("button", { name: testUser.display_name ?? testUser.username }));

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.getByLabelText("User menu")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View profile" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Workspace settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<UserMenu />);
    await user.click(screen.getByRole("button", { name: testUser.display_name ?? testUser.username }));
    expect(screen.getByLabelText("User menu")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByLabelText("User menu")).not.toBeInTheDocument();
  });

  it("closes when clicking a link inside it", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<UserMenu />);
    await user.click(screen.getByRole("button", { name: testUser.display_name ?? testUser.username }));

    await user.click(screen.getByRole("link", { name: "View profile" }));

    expect(screen.queryByLabelText("User menu")).not.toBeInTheDocument();
  });
});
