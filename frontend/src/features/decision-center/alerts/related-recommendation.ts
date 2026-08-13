import type { RecommendationCandidate } from "@/types/portfolio";

/**
 * `Alert` has no field linking it back to a `Recommendation` — only
 * `rule_id`/`ticker`/`signal_name` (confirmed against
 * `app/alerts/models.py`). This is a **client-side ticker match only**,
 * by explicit product decision: if a `RecommendationCandidate` sharing
 * the alert's ticker happens to be loaded in the same session, show it
 * as "related" — clearly labeled as inferred everywhere it's rendered,
 * never presented as a backend-asserted relationship (see
 * `docs/frontend/MILESTONE_5.md`).
 */
export function findRelatedRecommendation(
  ticker: string,
  candidates: RecommendationCandidate[] | undefined,
): RecommendationCandidate | null {
  if (!candidates) return null;
  return candidates.find((candidate) => candidate.ticker === ticker) ?? null;
}
