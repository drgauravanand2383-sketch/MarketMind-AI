import { create } from "zustand";

interface NetworkStatusState {
  online: boolean;
}

export const useNetworkStatusStore = create<NetworkStatusState>()(() => ({
  online: navigator.onLine,
}));

// Wired once at module load, not inside a component effect — same
// pattern `apiClient.setAuthHooks` (`src/app/providers.tsx`) already
// uses for other browser-global wiring.
window.addEventListener("online", () => {
  useNetworkStatusStore.setState({ online: true });
});
window.addEventListener("offline", () => {
  useNetworkStatusStore.setState({ online: false });
});
