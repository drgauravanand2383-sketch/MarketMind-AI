import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingButton } from "@/components/forms/loading-button";

describe("LoadingButton", () => {
  it("renders its children and is enabled when not loading", () => {
    render(<LoadingButton>Save</LoadingButton>);

    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute("aria-busy", "false");
  });

  it("disables itself, sets aria-busy, and shows loading text while loading", () => {
    render(
      <LoadingButton isLoading loadingText="Saving…">
        Save
      </LoadingButton>,
    );

    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});
