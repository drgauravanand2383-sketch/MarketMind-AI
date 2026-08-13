import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectivityPanel } from "@/features/dashboard/connectivity-panel";
import { renderWithQueryClient } from "@/test/test-utils";
import { useNetworkStatusStore } from "@/store/network-status-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";

describe("ConnectivityPanel", () => {
  beforeEach(() => {
    useNetworkStatusStore.setState({ online: true });
    useRealtimeConnectionStore.setState({ state: "disconnected", lastEventAt: null, lastHeartbeatAt: null, reconnect: () => {} });
  });

  it("resolves API connectivity to CONNECTED once the mocked health endpoint responds", async () => {
    renderWithQueryClient(<ConnectivityPanel />);
    await waitFor(
      () => {
        expect(screen.getAllByText("CONNECTED").length).toBeGreaterThan(0);
      },
      { timeout: 3000 },
    );
  });

  it("shows the WebSocket connection state from realtime-connection-store, not a direct useWebSocket call", () => {
    useRealtimeConnectionStore.setState({ state: "reconnecting" });
    renderWithQueryClient(<ConnectivityPanel />);
    expect(screen.getByText("RECONNECTING")).toBeInTheDocument();
  });

  it("shows last event/heartbeat timestamps once populated", () => {
    useRealtimeConnectionStore.setState({ lastEventAt: "2026-01-15T12:00:00Z", lastHeartbeatAt: "2026-01-15T12:00:05Z" });
    renderWithQueryClient(<ConnectivityPanel />);
    expect(screen.getByText(/Last event:/)).not.toHaveTextContent("Never");
    expect(screen.getByText(/Last heartbeat:/)).not.toHaveTextContent("Never");
  });

  it("shows a manual Reconnect button only when the connection has failed or is disconnected", () => {
    useRealtimeConnectionStore.setState({ state: "connected" });
    const { rerender } = renderWithQueryClient(<ConnectivityPanel />);
    expect(screen.queryByRole("button", { name: "Reconnect" })).not.toBeInTheDocument();

    useRealtimeConnectionStore.setState({ state: "failed" });
    rerender(<ConnectivityPanel />);
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
  });

  it("calls the store's reconnect action when Reconnect is clicked", async () => {
    let called = false;
    useRealtimeConnectionStore.setState({
      state: "failed",
      reconnect: () => {
        called = true;
      },
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ConnectivityPanel />);

    await user.click(screen.getByRole("button", { name: "Reconnect" }));

    expect(called).toBe(true);
  });

  it("announces the WebSocket connection state in a polite live region", () => {
    useRealtimeConnectionStore.setState({ state: "reconnecting" });
    renderWithQueryClient(<ConnectivityPanel />);
    expect(screen.getByText("WebSocket reconnecting")).toBeInTheDocument();
  });

  it("shows an offline banner when the browser reports offline, regardless of WS state", () => {
    useNetworkStatusStore.setState({ online: false });
    useRealtimeConnectionStore.setState({ state: "connected" });
    renderWithQueryClient(<ConnectivityPanel />);
    expect(screen.getByText(/You're offline/)).toBeInTheDocument();
  });
});
