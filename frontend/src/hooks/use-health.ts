import { useQuery } from "@tanstack/react-query";
import { systemApi } from "@/services/api/system-api";

const HEALTH_POLL_INTERVAL_MS = 15_000;

export function useHealth() {
  return useQuery({
    queryKey: ["system", "health"],
    queryFn: systemApi.getHealth,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
    retry: false,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["system", "ready"],
    queryFn: systemApi.getReadiness,
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
    retry: false,
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["system", "version"],
    queryFn: systemApi.getVersion,
    staleTime: Number.POSITIVE_INFINITY, // the running deployment's version never changes mid-session
  });
}
