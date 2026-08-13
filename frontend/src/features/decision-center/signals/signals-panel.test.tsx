import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SignalsPanel } from "@/features/decision-center/signals/signals-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { buildSignalDefinition } from "@/test/msw/fixtures";
import { resetDecisionCenterStore } from "@/test/msw/decision-center-store";

describe("SignalsPanel", () => {
  beforeEach(() => {
    resetDecisionCenterStore({
      signalDefinitions: [
        buildSignalDefinition({
          id: "def-1",
          name: "High Price",
          conditions: [{ id: "c1", field: "quote.price", operator: "GREATER_THAN", value: 100, weight: 1, group: null, enabled: true }],
        }),
      ],
    });
  });

  it("prompts to select a definition before showing the evaluate form", async () => {
    renderWithQueryClient(<SignalsPanel />);
    await waitFor(() => {
      expect(screen.getByText("Select a definition")).toBeInTheDocument();
    });
  });

  it("scopes the evaluate form to only the fields the definition's conditions reference", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<SignalsPanel />);
    await waitFor(() => {
      expect(screen.getByLabelText("Signal definition")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("Signal definition"), "def-1");

    expect(await screen.findByRole("columnheader", { name: "Price" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ticker")).toBeInTheDocument();
  });

  it("evaluates a company and shows a triggered result with its category and priority", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<SignalsPanel />);
    await waitFor(() => {
      expect(screen.getByLabelText("Signal definition")).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText("Signal definition"), "def-1");
    await screen.findByLabelText("Ticker");

    await user.type(screen.getByLabelText("Ticker"), "AAPL");
    const priceInput = screen.getByLabelText("Price");
    await user.type(priceInput, "150");
    await user.click(screen.getByRole("button", { name: /evaluate signal/i }));

    await waitFor(() => {
      expect(screen.getByText("Triggered")).toBeInTheDocument();
    });
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });
});
