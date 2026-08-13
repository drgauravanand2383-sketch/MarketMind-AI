export interface LatencyPoint {
  time: string;
  latencyMs: number;
}

/** Demo data only — the backend doesn't track/expose response-time
 * history (M2 spec: "consume mocked/demo data only unless live backend
 * endpoints already exist"). Unlike the two health charts, there is no
 * real endpoint this could be derived from yet. */
export const MOCK_API_LATENCY: LatencyPoint[] = [
  { time: "09:00", latencyMs: 42 },
  { time: "09:15", latencyMs: 38 },
  { time: "09:30", latencyMs: 51 },
  { time: "09:45", latencyMs: 47 },
  { time: "10:00", latencyMs: 60 },
  { time: "10:15", latencyMs: 44 },
  { time: "10:30", latencyMs: 39 },
];
