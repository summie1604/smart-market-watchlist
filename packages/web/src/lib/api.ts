/**
 * The API view model, as the backend serves it.
 *
 * Mirrored here as types only. The frontend renders these verdicts; it never computes
 * one (DESIGN.md D2) — there is no scoring, no thresholding and no ranking in this
 * package, and there should never be.
 */

export type Attention =
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "NO_MEANINGFUL_CHANGE"
  | "UNABLE_TO_EVALUATE_RELIABLY";

export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface Reason {
  code: string;
  direction: "+" | "-";
  contribution: number;
  detail: string;
}

export interface CoverageRecord {
  source: string;
  status: string;
  detail: string;
}

export interface Coverage {
  complete: boolean;
  note: string;
  records: CoverageRecord[];
}

export interface EvidenceRef {
  source: string;
  ref: string;
  tier: string;
  publisher: string;
  subject_company: string;
  published_at: string;
  url: string;
}

/** Independent publishers, not article count (D13). Repetition is not confirmation. */
export interface Corroboration {
  article_count: number;
  independent_source_count: number;
  summary: string;
  has_authoritative: boolean;
}

export interface Assessment {
  event_id: string;
  symbol: string;
  company: string;
  event_type: string;
  description: string;
  occurred_at: string;
  attention: Attention;
  confidence: Confidence;
  score: number;
  scoring_version: string;
  reasons: Reason[];
  coverage: Coverage;
  corroboration: Corroboration;
  evidence: EvidenceRef[];
}

/** Source health for the most recent ingest, independent of any assessment. */
export interface SourceHealth {
  run_id: string;
  source: string;
  started_at: string;
  assessed_count: number;
  healthy: boolean;
  records: CoverageRecord[];
}

export interface AssessmentsResponse {
  count: number;
  /** `null` means we have never run — which is not the same as running and failing. */
  source_health: SourceHealth | null;
  assessments: Assessment[];
}

/**
 * Where the API lives. Configurable so a demo off the build machine does not need a
 * source edit; the default keeps `make run` working with no configuration at all.
 */
export const API_BASE = import.meta.env.PUBLIC_API_BASE ?? "http://localhost:8000";

/** Human wording for a verdict. A conclusion and an admission never read alike. */
export function attentionLabel(attention: Attention): string {
  switch (attention) {
    case "NO_MEANINGFUL_CHANGE":
      return "No meaningful change";
    case "UNABLE_TO_EVALUATE_RELIABLY":
      return "Unable to evaluate reliably";
    default:
      return `${attention} attention`;
  }
}

/**
 * Fetch the ranked assessments and current source health.
 *
 * The order is the engine's answer to a product question and is rendered unchanged.
 * This module deliberately exposes no default sort of its own (DESIGN.md D2).
 */
export async function fetchAssessments(limit = 50): Promise<AssessmentsResponse> {
  const response = await fetch(`${API_BASE}/assessments?limit=${limit}`);
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return (await response.json()) as AssessmentsResponse;
}

/** A sort the reader asked for. `null` means "leave the backend's ranking alone". */
export type ViewSort = "company" | "recency" | "confidence" | null;

const CONFIDENCE_ORDER: Record<Confidence, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/**
 * Apply a reader-selected view sort.
 *
 * Canonical product ranking belongs to the backend; this exists only for sorts a person
 * explicitly asks for. With no selection it returns the given order untouched — it must
 * never become a second, divergent answer to "what deserves attention first".
 */
export function applyViewSort(assessments: Assessment[], sort: ViewSort): Assessment[] {
  if (sort === null) return assessments;
  const sorted = [...assessments];
  switch (sort) {
    case "company":
      return sorted.sort((a, b) => a.symbol.localeCompare(b.symbol));
    case "recency":
      return sorted.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
    case "confidence":
      return sorted.sort(
        (a, b) => CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence],
      );
  }
}
