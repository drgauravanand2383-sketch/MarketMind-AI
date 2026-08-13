import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitForElementToBeRemoved } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationCenter } from "@/components/notifications/notification-center";
import { notify, useNotificationStore } from "@/store/notification-store";

describe("NotificationCenter", () => {
  beforeEach(() => {
    useNotificationStore.setState({ notifications: [] });
  });

  it("renders a toast with the correct live-region role per type", () => {
    notify("error", "Something broke.", { durationMs: 0 });
    render(<NotificationCenter />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something broke.");
  });

  it("uses a polite status role for non-urgent notification types", () => {
    notify("success", "Saved successfully.", { durationMs: 0 });
    render(<NotificationCenter />);

    expect(screen.getByRole("status")).toHaveTextContent("Saved successfully.");
  });

  it("dismisses a toast when its dismiss button is clicked", async () => {
    const user = userEvent.setup();
    notify("info", "FYI.", { durationMs: 0 });
    render(<NotificationCenter />);

    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));

    // The toast's exit is an animated (Framer Motion) unmount, not an
    // instant DOM removal — wait for it rather than asserting synchronously.
    await waitForElementToBeRemoved(() => screen.queryByText("FYI."));
  });
});
