import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FormField } from "@/components/forms/form-field";

describe("FormField", () => {
  it("associates the label with the input via htmlFor/id", () => {
    render(<FormField label="Username" />);

    expect(screen.getByLabelText("Username")).toBeInTheDocument();
  });

  it("links an error to the input via aria-describedby and marks it invalid", () => {
    render(<FormField label="Email" error="Email is required" />);

    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(screen.getByRole("alert")).toHaveTextContent("Email is required");
    expect(document.getElementById(describedBy ?? "")).toHaveTextContent("Email is required");
  });

  it("does not mark the input invalid when there is no error", () => {
    render(<FormField label="Email" />);

    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
  });
});
