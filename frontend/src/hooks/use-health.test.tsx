import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { useHealth, useVersion } from "@/hooks/use-health";
import { renderWithQueryClient } from "@/test/test-utils";

function Probe({ hook }: { hook: () => { data: unknown; isSuccess: boolean } }): ReactElement {
  const result = hook();
  return <div data-testid="probe">{result.isSuccess ? JSON.stringify(result.data) : "loading"}</div>;
}

describe("useHealth / useVersion", () => {
  it("resolves the mocked application health", async () => {
    const { getByTestId } = renderWithQueryClient(<Probe hook={useHealth} />);

    await waitFor(() => {
      expect(getByTestId("probe").textContent).toContain("HEALTHY");
    });
  });

  it("resolves the mocked version", async () => {
    const { getByTestId } = renderWithQueryClient(<Probe hook={useVersion} />);

    await waitFor(() => {
      expect(getByTestId("probe").textContent).toContain("1.0.0");
    });
  });
});
