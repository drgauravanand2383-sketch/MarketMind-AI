import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "@/components/button";

describe("Button", () => {
  it("defaults to a type=\"button\" primary/md button, so it never accidentally submits a form", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");
    expect(button.className).toContain("bg-brand-600");
    expect(button.className).toContain("px-3 py-2 text-sm");
  });

  it("applies the requested variant and size classes", () => {
    render(
      <Button variant="destructive-outline" size="sm">
        Reset
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Reset" });
    expect(button.className).toContain("border-red-300");
    expect(button.className).toContain("px-2.5 py-1.5 text-xs");
  });

  it("forwards onClick and other native button props", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled={false}>
        Click me
      </Button>,
    );

    await user.click(screen.getByRole("button", { name: "Click me" }));

    expect(onClick).toHaveBeenCalledOnce();
  });
});
