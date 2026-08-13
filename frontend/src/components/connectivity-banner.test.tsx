import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ConnectivityBanner } from "@/components/connectivity-banner";
import { renderWithQueryClient } from "@/test/test-utils";
import { useNetworkStatusStore } from "@/store/network-status-store";
import { useRealtimeConnectionStore } from "@/store/realtime-connection-store";

describe("ConnectivityBanner", () => {
  beforeEach(() => {
    useNetworkStatusStore.setState({ online: true });
    useRealtimeConnectionStore.setState({ state: "connected", lastEventAt: null, lastHeartbeatAt: null, reconnect: () => {} });
  });

  it("renders nothing once online, connected, and healthy", async () => {
    renderWithQueryClient(<ConnectivityBanner />);
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("shows an offline message when the browser reports offline, from any page", () => {
    useNetworkStatusStore.setState({ online: false });
    renderWithQueryClient(<ConnectivityBanner />);
    expect(screen.getByRole("status")).toHaveTextContent(/you're offline/i);
  });

  it("shows an unreachable message when the WebSocket connection has failed, even while online", () => {
    useRealtimeConnectionStore.setState({ state: "failed" });
    renderWithQueryClient(<ConnectivityBanner />);
    expect(screen.getByRole("status")).toHaveTextContent(/real-time connection unavailable/i);
  });
});
