import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { ResearchBatchPage } from "@/features/research/research-batch-page";
import { renderWithQueryClient } from "@/test/test-utils";
import { researchReportStore } from "@/test/msw/handlers";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return { ...actual, Link: (props: { to: string; children?: ReactNode }) => <a href={props.to}>{props.children}</a> };
});

describe("ResearchBatchPage", () => {
  beforeEach(() => {
    researchReportStore.reset();
  });

  it("starts with one company row and disables Remove when only one remains", () => {
    renderWithQueryClient(<ResearchBatchPage />);
    expect(screen.getByLabelText("Company 1 name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove company 1" })).toBeDisabled();
  });

  it("adds and removes company rows", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResearchBatchPage />);

    await user.click(screen.getByRole("button", { name: "Add company" }));
    expect(screen.getByLabelText("Company 2 name")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove company 2" }));
    expect(screen.queryByLabelText("Company 2 name")).not.toBeInTheDocument();
  });

  it("rejects submission when a company name is blank", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResearchBatchPage />);

    await user.click(screen.getByRole("button", { name: /run batch research/i }));

    expect(await screen.findByText("Required")).toBeInTheDocument();
  });

  it("runs batch research and lists each result with a matched/unmatched badge", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ResearchBatchPage />);

    await user.type(screen.getByLabelText("Company 1 name"), "Apple Inc.");
    await user.click(screen.getByRole("button", { name: "Add company" }));
    await user.type(screen.getByLabelText("Company 2 name"), "Microsoft");

    await user.click(screen.getByRole("button", { name: /run batch research/i }));

    await waitFor(() => {
      expect(screen.getAllByText("Matched")).toHaveLength(2);
    });
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("Microsoft")).toBeInTheDocument();
  });
});
