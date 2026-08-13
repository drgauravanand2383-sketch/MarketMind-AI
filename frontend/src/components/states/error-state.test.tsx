import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorState } from "@/components/states/error-state";

describe("ErrorState", () => {
  it("renders the message with an alert role", () => {
    render(<ErrorState message="Could not load data." />);

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load data.");
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState message="Failed." onRetry={onRetry} />);

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders no retry button when onRetry is not supplied", () => {
    render(<ErrorState message="Failed." />);

    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
