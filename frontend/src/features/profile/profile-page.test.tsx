import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ProfilePage } from "@/features/profile/profile-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { testUser } from "@/test/msw/fixtures";
import { API_BASE_URL } from "@/services/api/config";
import { useAuthStore } from "@/store/auth-store";
import { usePreferencesStore } from "@/store/preferences-store";

describe("ProfilePage", () => {
  beforeEach(() => {
    usePreferencesStore.getState().resetAll();
    useAuthStore.setState({
      status: "authenticated",
      user: { ...testUser, display_name: "Alice Example", roles: ["analyst"], permissions: ["portfolio:read", "watchlist:read"] },
      accessToken: {
        token: "secret-access-token-value",
        token_type: "access",
        subject: testUser.id,
        token_id: "access-1",
        issued_at: "2026-01-01T00:00:00Z",
        expires_at: "2026-01-01T00:15:00Z",
      },
      refreshToken: {
        token: "secret-refresh-token-value",
        subject: testUser.id,
        token_id: "refresh-1",
        issued_at: "2026-01-01T00:00:00Z",
        expires_at: "2026-01-08T00:00:00Z",
      },
    });
  });

  it("shows account summary, user information, and session information", async () => {
    renderWithQueryClient(<ProfilePage />);

    expect(screen.getByRole("heading", { name: "Alice Example" })).toBeInTheDocument();
    expect(screen.getAllByText(testUser.email).length).toBeGreaterThan(0);
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("analyst")).toBeInTheDocument();
    expect(screen.getByText("2 granted")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Connected API")).toBeInTheDocument();
    });
  });

  it("never displays the raw access or refresh token value", () => {
    renderWithQueryClient(<ProfilePage />);

    expect(screen.queryByText("secret-access-token-value")).not.toBeInTheDocument();
    expect(screen.queryByText("secret-refresh-token-value")).not.toBeInTheDocument();
  });

  it("shows the connected API base URL and, once resolved, the version", async () => {
    renderWithQueryClient(<ProfilePage />);

    await waitFor(() => {
      expect(screen.getByText("1.0.0")).toBeInTheDocument();
    });
    expect(screen.getByText("test")).toBeInTheDocument();
    expect(screen.getByText(API_BASE_URL)).toBeInTheDocument();
  });
});
