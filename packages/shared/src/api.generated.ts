/**
 * GENERATED — do not edit.
 *
 * The wire contract, produced from the backend's OpenAPI schema by
 * `packages/backend/scripts/generate_api_types.py` (`make api-types`).
 *
 * Every client renders these verdicts; none of them computes one. Attention, confidence,
 * coverage, corroboration, canonical order and contradiction state all arrive decided.
 *
 * API version: v1
 */

export const API_VERSION = "v1";

export const API_PREFIX = "/v1";

export interface AccountView {
  user_id: string;
  email: string;
  demo_mode: boolean;
  is_demo: boolean;
  transport: "cookie" | "bearer";
}

export interface AssessmentView {
  event_id: string;
  symbol: string;
  company: string;
  event_type: string;
  description: string;
  occurred_at: string;
  attention:
    | "HIGH"
    | "MEDIUM"
    | "LOW"
    | "NO_MEANINGFUL_CHANGE"
    | "UNABLE_TO_EVALUATE_RELIABLY";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  score: number;
  scoring_version: string;
  reasons: ReasonView[];
  coverage: CoverageView;
  corroboration: CorroborationView;
  evidence: EvidenceRefView[];
  contradiction: ContradictionView;
  source_standing:
    | "OFFICIAL"
    | "ESTABLISHED"
    | "SYNDICATED_RELEASE"
    | "UNRECOGNISED"
    | "COMPUTED";
  source_standing_label: string;
  focus: FocusMatchView[];
}

export interface AssessmentsResponse {
  count: number;
  source_health: RunView | null;
  runs: RunView[];
  assessments: AssessmentView[];
}

export interface AssistantAnswerView {
  scope: "company" | "watchlist";
  symbol: string | null;
  company: string | null;
  question: string;
  intent: string;
  answered: boolean;
  window: ExplainerWindowView;
  coverage: CoverageView;
  statements: ExplainerStatementView[];
  evidence: EvidenceRefView[];
  insufficient_reason: string | null;
  suggestions: string[];
  generated_by: string;
  disclaimer: string;
}

export interface AssistantRequest {
  question: string;
  symbol?: string | null;
}

export interface AttentionItemView {
  symbol: string;
  company: string;
  assessment: AssessmentView;
  development_id: string;
  development_sources: number;
}

export interface CompleteRequest {
  review_id: string;
}

export interface CompleteReviewResponse {
  checkpoint: string;
  outcome: "advanced" | "already-at-this-cutoff" | "stale-cutoff-ignored";
}

export interface ContradictionView {
  state: "STANDING" | "DISPUTED" | "WITHDRAWN";
  disputed_by: string | null;
  detail: string;
  confirmed: boolean;
}

export interface CorroborationView {
  article_count: number;
  independent_source_count: number;
  summary: string;
  has_authoritative: boolean;
}

export interface CoverageRecordView {
  source: string;
  status: string;
  detail: string;
}

export interface CoverageView {
  complete: boolean;
  note: string;
  records: CoverageRecordView[];
}

export interface Credentials {
  email: string;
  password: string;
  transport?: "cookie" | "bearer";
}

export interface EvidenceRefView {
  source: string;
  ref: string;
  tier: string;
  publisher: string;
  standing:
    | "OFFICIAL"
    | "ESTABLISHED"
    | "SYNDICATED_RELEASE"
    | "UNRECOGNISED"
    | "COMPUTED";
  standing_label: string;
  subject_company: string;
  published_at: string;
  url: string;
}

export interface ExplainRequest {
  question: string;
}

export interface ExplainerAnswerView {
  symbol: string;
  company: string;
  question: string;
  intent: string;
  answered: boolean;
  window: ExplainerWindowView;
  coverage: CoverageView;
  statements: ExplainerStatementView[];
  evidence: EvidenceRefView[];
  insufficient_reason: string | null;
  suggestions: string[];
  generated_by: string;
  disclaimer: string;
}

export interface ExplainerStatementView {
  text: string;
  event_ids: string[];
}

export interface ExplainerWindowView {
  from: string | null;
  to: string;
  basis: string;
  assessments_considered: number;
}

export interface FocusMatchView {
  tag: string;
  label: string;
  why: string;
}

export interface FocusTagView {
  tag: string;
  label: string;
  because: string;
}

export interface FocusTagsResponse {
  tags: FocusTagView[];
}

export interface IngestResponse {
  outcome: string;
  assessed: number;
  healthy_families: string[];
  failed_families: string[];
  runs: RunView[];
}

export interface MetaResponse {
  api_version: string;
  scoring_version: string;
  mode: "live" | "judge";
  demo_mode: boolean;
  attention_levels: string[];
  confidence_levels: string[];
  contradiction_states: string[];
  focus_tags: string[];
  price_ranges: string[];
  source_families: string[];
}

export interface PriceComparisonView {
  symbol: string;
  range: string;
  basis: string;
  sessions: number;
  covered_from: string | null;
  covered_to: string | null;
  notes: string[];
  source_detail: string;
  series: PriceSeriesView[];
}

export interface PricePointView {
  on: string;
  value: number;
}

export interface PriceSeriesView {
  symbol: string;
  label: string;
  role: "security" | "sector" | "broad";
  change_pct: number;
  points: PricePointView[];
}

export interface PriceSessionView {
  on: string;
  close: number;
}

export interface PriceStatusView {
  symbol: string;
  as_of: string | null;
  close: number | null;
  daily_change: number | null;
  daily_change_pct: number | null;
  day_high: number | null;
  day_low: number | null;
  day_volume: number | null;
  points: number[];
  sessions: PriceSessionView[];
}

export interface PriceStatusesResponse {
  statuses: PriceStatusView[];
}

export interface ReasonView {
  code: string;
  direction: "+" | "-";
  contribution: number;
  detail: string;
}

export interface RemovedResponse {
  symbol: string;
  removed: boolean;
}

export interface ReviewLineView {
  symbol: string;
  company: string;
  coverage_tier: string;
  state: "changed" | "quiet" | "unable" | "new";
  detail: string;
  assessments: AssessmentView[];
}

export interface ReviewPageView {
  review_id: string;
  previous_checkpoint: string | null;
  review_cutoff: string;
  attention_count: number;
  needs_attention: AttentionItemView[];
  triggered_watch_points: WatchPointView[];
  changed: ReviewLineView[];
  newly_added: ReviewLineView[];
  unable: ReviewLineView[];
  quiet: ReviewLineView[];
}

export interface RunView {
  run_id: string;
  source: string;
  started_at: string;
  assessed_count: number;
  healthy: boolean;
  records: CoverageRecordView[];
}

export interface SchedulerResponse {
  enabled: boolean;
  started: boolean;
  cycle_active: boolean;
  interval_seconds: number;
  cycles_completed: number;
  next_run_at?: string | null;
  last_cycle?: Record<string, unknown> | null;
}

export interface SessionView {
  user_id: string;
  email: string;
  transport: "cookie" | "bearer";
  expires_at: string;
  session?: string | null;
}

export interface StatusResponse {
  status: string;
}

export interface SymbolRequest {
  symbol: string;
  reason?: string;
  watch_for?: string;
  tags?: string[];
}

export interface UniverseCompanyView {
  symbol: string;
  company: string;
  coverage_tier: string;
}

export interface UniverseResponse {
  companies: UniverseCompanyView[];
}

export interface WatchPointRequest {
  level?: number | null;
  percent?: number | null;
  note?: string;
}

export interface WatchPointView {
  point_id: string;
  symbol: string;
  company: string;
  level: number;
  direction: "ABOVE" | "BELOW" | "PERCENT_UP" | "PERCENT_DOWN";
  note: string;
  created_at: string;
  created_close: number | null;
  triggered_on: string | null;
  triggered_close: number | null;
  acknowledged_at: string | null;
  needs_attention: boolean;
}

export interface WatchPointsResponse {
  points: WatchPointView[];
}

export interface WatchedCompanyView {
  symbol: string;
  company: string;
  coverage_tier: string;
  added_at: string;
  watched_from: string;
  sector_index: string | null;
  sector_label: string | null;
  reason: string;
  watch_for: string;
  tags: string[];
}

export interface WatchlistResponse {
  companies: WatchedCompanyView[];
}
