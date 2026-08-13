import { beforeEach, describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { PreferencesProvider } from "@/app/preferences-provider";
import { usePreferencesStore } from "@/store/preferences-store";

describe("PreferencesProvider", () => {
  beforeEach(() => {
    usePreferencesStore.getState().resetAll();
    document.documentElement.className = "";
  });

  it("renders children", () => {
    render(
      <PreferencesProvider>
        <p>Hello</p>
      </PreferencesProvider>,
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("toggles the compact class on <html> when density changes", () => {
    render(
      <PreferencesProvider>
        <p>content</p>
      </PreferencesProvider>,
    );
    expect(document.documentElement.classList.contains("compact")).toBe(false);

    act(() => {
      usePreferencesStore.getState().setDensity("compact");
    });

    expect(document.documentElement.classList.contains("compact")).toBe(true);
  });

  it("toggles high-contrast/large-text/focus-highlight classes independently", () => {
    render(
      <PreferencesProvider>
        <p>content</p>
      </PreferencesProvider>,
    );

    act(() => {
      usePreferencesStore.getState().setHighContrast(true);
    });
    expect(document.documentElement.classList.contains("high-contrast")).toBe(true);
    expect(document.documentElement.classList.contains("large-text")).toBe(false);

    act(() => {
      usePreferencesStore.getState().setLargeText(true);
    });
    expect(document.documentElement.classList.contains("large-text")).toBe(true);

    act(() => {
      usePreferencesStore.getState().setFocusHighlight(true);
    });
    expect(document.documentElement.classList.contains("focus-highlight")).toBe(true);
  });
});
