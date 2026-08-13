import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { screeningApi } from "@/services/api/screening-api";
import { notify } from "@/store/notification-store";
import { useSessionActivityStore } from "@/store/session-activity-store";
import type { PaginatedResponse } from "@/types/api";
import type {
  CreateScreeningProfileRequest,
  DuplicateScreeningProfileRequest,
  ListScreeningProfilesParams,
  RunScreeningRequest,
  ScreeningProfile,
  UpdateScreeningProfileRequest,
} from "@/types/screening";

export const screeningKeys = {
  all: ["screening", "profiles"] as const,
  lists: () => [...screeningKeys.all, "list"] as const,
  list: (params: ListScreeningProfilesParams) => [...screeningKeys.lists(), params] as const,
  details: () => [...screeningKeys.all, "detail"] as const,
  detail: (id: string) => [...screeningKeys.details(), id] as const,
  results: () => ["screening", "results"] as const,
  result: (id: string) => [...screeningKeys.results(), id] as const,
};

export function useScreeningProfilesList(params: ListScreeningProfilesParams) {
  return useQuery({
    queryKey: screeningKeys.list(params),
    queryFn: () => screeningApi.listProfiles(params),
    placeholderData: (previous) => previous,
  });
}

export function useScreeningProfile(profileId: string) {
  return useQuery({
    queryKey: screeningKeys.detail(profileId),
    queryFn: () => screeningApi.getProfile(profileId),
    enabled: profileId.length > 0,
  });
}

/** `GET /screening/results/{result_id}` only resolves for an id this
 * same backend process cached (in-memory store, see
 * `docs/architecture/INTELLIGENCE_API.md` §2) — a 404 here means "no
 * longer available," not a generic error. */
export function useScreeningResult(resultId: string) {
  return useQuery({
    queryKey: screeningKeys.result(resultId),
    queryFn: () => screeningApi.getResult(resultId),
    enabled: resultId.length > 0,
  });
}

function patchProfileInCache(queryClient: QueryClient, updated: ScreeningProfile): void {
  queryClient.setQueryData(screeningKeys.detail(updated.id), updated);
  queryClient.setQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() }, (page) => {
    if (!page) return page;
    return { ...page, data: page.data.map((p) => (p.id === updated.id ? updated : p)) };
  });
}

function removeProfileFromCache(queryClient: QueryClient, profileId: string): void {
  queryClient.removeQueries({ queryKey: screeningKeys.detail(profileId) });
  queryClient.setQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() }, (page) => {
    if (!page) return page;
    return { ...page, data: page.data.filter((p) => p.id !== profileId), total: Math.max(0, page.total - 1) };
  });
}

interface ProfileMutationSnapshot {
  previousDetail: ScreeningProfile | undefined;
  previousLists: (readonly [readonly unknown[], PaginatedResponse<ScreeningProfile> | undefined])[];
}

/** Cancels in-flight queries first so a server response can't land mid-
 * optimistic-write and get silently overwritten by it — same convention
 * as `snapshotWatchlistCaches` in `use-watchlists.ts`. */
async function snapshotProfileCaches(queryClient: QueryClient, profileId: string): Promise<ProfileMutationSnapshot> {
  await queryClient.cancelQueries({ queryKey: screeningKeys.detail(profileId) });
  await queryClient.cancelQueries({ queryKey: screeningKeys.lists() });
  return {
    previousDetail: queryClient.getQueryData<ScreeningProfile>(screeningKeys.detail(profileId)),
    previousLists: queryClient.getQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() }),
  };
}

function rollbackProfileCaches(queryClient: QueryClient, profileId: string, snapshot: ProfileMutationSnapshot): void {
  if (snapshot.previousDetail) {
    queryClient.setQueryData(screeningKeys.detail(profileId), snapshot.previousDetail);
  }
  for (const [key, data] of snapshot.previousLists) {
    queryClient.setQueryData(key, data);
  }
}

function findProfileInCaches(queryClient: QueryClient, profileId: string): ScreeningProfile | undefined {
  const detail = queryClient.getQueryData<ScreeningProfile>(screeningKeys.detail(profileId));
  if (detail) return detail;
  const lists = queryClient.getQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() });
  for (const [, page] of lists) {
    const match = page?.data.find((p) => p.id === profileId);
    if (match) return match;
  }
  return undefined;
}

export function useCreateScreeningProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateScreeningProfileRequest) => screeningApi.createProfile(body),
    onSuccess: (profile) => {
      void queryClient.invalidateQueries({ queryKey: screeningKeys.lists() });
      notify("success", `Screen "${profile.name}" created.`);
    },
  });
}

/** Covers both a plain rename and a full builder save (filters/groups) —
 * both are a whole-object `PATCH`, so one optimistic hook serves both. */
export function useUpdateScreeningProfile(profileId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateScreeningProfileRequest) => screeningApi.updateProfile(profileId, body),
    meta: { suppressErrorToast: true },
    onMutate: async (body): Promise<ProfileMutationSnapshot> => {
      const snapshot = await snapshotProfileCaches(queryClient, profileId);
      if (snapshot.previousDetail) {
        patchProfileInCache(queryClient, { ...snapshot.previousDetail, ...body });
      }
      return snapshot;
    },
    onError: (_error, _body, snapshot) => {
      if (snapshot) rollbackProfileCaches(queryClient, profileId, snapshot);
      notify("error", "Couldn't update the profile — change was rolled back.");
    },
    onSuccess: (profile) => {
      patchProfileInCache(queryClient, profile);
      notify("success", `Profile "${profile.name}" updated.`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: screeningKeys.detail(profileId) });
    },
  });
}

/** Optimistically inserts a temporary profile row at the top of every
 * cached list page, then swaps it for the real one on success (or drops
 * it and restores the snapshot on failure). Unlike rename/update, there
 * is no existing detail cache entry to patch — this creates a new
 * resource, so the optimistic value is synthesized from the source
 * profile plus the new name. */
export function useDuplicateScreeningProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ profileId, body }: { profileId: string; body: DuplicateScreeningProfileRequest }) =>
      screeningApi.duplicateProfile(profileId, body),
    meta: { suppressErrorToast: true },
    onMutate: async ({ profileId, body }) => {
      await queryClient.cancelQueries({ queryKey: screeningKeys.lists() });
      const previousLists = queryClient.getQueriesData<PaginatedResponse<ScreeningProfile>>({
        queryKey: screeningKeys.lists(),
      });
      const source = findProfileInCaches(queryClient, profileId);
      const tempId = `optimistic-${crypto.randomUUID()}`;
      if (source) {
        const now = new Date().toISOString();
        const optimisticProfile: ScreeningProfile = { ...source, id: tempId, name: body.new_name, created_at: now, updated_at: now };
        queryClient.setQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() }, (page) => {
          if (!page) return page;
          return { ...page, data: [optimisticProfile, ...page.data], total: page.total + 1 };
        });
      }
      return { previousLists, tempId };
    },
    onError: (_error, _vars, context) => {
      if (context) {
        for (const [key, data] of context.previousLists) {
          queryClient.setQueryData(key, data);
        }
      }
      notify("error", "Couldn't duplicate the profile — change was rolled back.");
    },
    onSuccess: (profile, _vars, context) => {
      queryClient.setQueriesData<PaginatedResponse<ScreeningProfile>>({ queryKey: screeningKeys.lists() }, (page) => {
        if (!page) return page;
        return { ...page, data: page.data.map((p) => (p.id === context.tempId ? profile : p)) };
      });
      notify("success", `"${profile.name}" created as a duplicate.`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: screeningKeys.lists() });
    },
  });
}

export function useDeleteScreeningProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => screeningApi.deleteProfile(profileId),
    meta: { suppressErrorToast: true },
    onMutate: async (profileId): Promise<ProfileMutationSnapshot> => {
      const snapshot = await snapshotProfileCaches(queryClient, profileId);
      removeProfileFromCache(queryClient, profileId);
      return snapshot;
    },
    onError: (_error, profileId, snapshot) => {
      if (snapshot) rollbackProfileCaches(queryClient, profileId, snapshot);
      notify("error", "Couldn't delete the profile — it has been restored.");
    },
    onSuccess: () => {
      notify("success", "Profile deleted.");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: screeningKeys.lists() });
    },
  });
}

/** No WebSocket event exists for screening progress (`POST /screening/run`
 * is synchronous request/response only) — the mutation's own `isPending`
 * state is what pages should use to render an indeterminate loading
 * indicator. */
export function useRunScreening(profileName: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RunScreeningRequest) => screeningApi.run(body),
    onMutate: (body) => {
      notify("info", `Running "${profileName}" against ${String(body.companies.length)} companies...`);
    },
    onSuccess: (envelope) => {
      queryClient.setQueryData(screeningKeys.result(envelope.result_id), envelope);
      useSessionActivityStore.getState().addScreeningRun({
        resultId: envelope.result_id,
        profileId: envelope.profile_id,
        profileName,
        companyCount: envelope.results.length,
        matchedCount: envelope.results.filter((r) => r.passed).length,
        ranAt: new Date().toISOString(),
      });
      notify("success", `Screen complete — ${String(envelope.results.filter((r) => r.passed).length)} of ${String(envelope.results.length)} companies matched.`);
    },
  });
}
