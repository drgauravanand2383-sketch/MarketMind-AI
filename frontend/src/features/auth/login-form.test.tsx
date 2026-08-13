import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { LoginForm } from "@/features/auth/login-form";
import { renderWithQueryClient } from "@/test/test-utils";

const navigateSpy = vi.fn();
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, useNavigate: () => navigateSpy };
});

describe("LoginForm", () => {
  it("rejects an empty submission with client-side validation, before any request is sent", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<LoginForm />);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Username is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
  });

  it("logs in with valid credentials and navigates to the dashboard", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<LoginForm />);

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalledWith({ to: "/" });
    });
  });
});
