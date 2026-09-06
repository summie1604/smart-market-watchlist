/** Thin HTTP client over the generated v1 wire contract. */

import { API_PREFIX } from "@smart-market-watchlist/shared";
import type {
  AccountView,
  AssistantAnswerView,
  MetaResponse,
  ExplainerAnswerView,
  ExplainerStatementView,
  AssessmentView,
  AssessmentsResponse as GeneratedAssessmentsResponse,
  AttentionItemView,
  CompleteReviewResponse,
  FocusTagView,
  PriceComparisonView,
  PricePointView,
  PriceSeriesView,
  PriceSessionView,
  WatchPointView,
  PriceStatusView,
  RemovedResponse,
  ReviewLineView,
  ReviewPageView,
  UniverseCompanyView,
  UniverseResponse,
  WatchedCompanyView,
  WatchlistResponse,
} from "@smart-market-watchlist/shared";

export type Account = AccountView;
export type Assessment = AssessmentView;
export type AssessmentsResponse = GeneratedAssessmentsResponse;
export type Attention = AssessmentView["attention"];
export type AttentionItem = AttentionItemView;
export type Confidence = AssessmentView["confidence"];
export type AssistantAnswer = AssistantAnswerView;
export type Meta = MetaResponse;
export type ExplainerAnswer = ExplainerAnswerView;
export type ExplainerStatement = ExplainerStatementView;
export type FocusTagInfo = FocusTagView;
export type PriceComparison = PriceComparisonView;
export type PricePoint = PricePointView;
export type PriceRange = PriceComparisonView["range"];
export type PriceSeries = PriceSeriesView;
export type PriceSession = PriceSessionView;
export type WatchPoint = WatchPointView;
export type PriceStatus = PriceStatusView;
export type ReviewLine = ReviewLineView;
export type ReviewPage = ReviewPageView;
export type UniverseCompany = UniverseCompanyView;
export type WatchedCompany = WatchedCompanyView;

export interface Interests {
  reason?: string;
  watch_for?: string;
  tags?: string[];
}

export const API_BASE = import.meta.env.PUBLIC_API_BASE ?? "http://localhost:8000";

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

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export async function fetchAssessments(limit = 50): Promise<AssessmentsResponse> {
  return call<AssessmentsResponse>(`/assessments?limit=${limit}`);
}

export const auth = {
  me: () => call<Account>("/auth/me"),
  register: (email: string, password: string) =>
    call<Account>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    call<Account>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => call<{ status: string }>("/auth/logout", { method: "POST" }),
};

export const universe = {
  list: () => call<UniverseResponse>("/universe"),
};

export const intelligence = {
  all: (limit = 400) => call<AssessmentsResponse>(`/assessments?limit=${limit}`),
};

export const watchlist = {
  list: () => call<WatchlistResponse>("/watchlist"),
  add: (symbol: string, interests: Interests = {}) =>
    call<WatchedCompany>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ symbol, ...interests }),
    }),
  remove: (symbol: string) =>
    call<RemovedResponse>(`/watchlist/${symbol}`, { method: "DELETE" }),
};

export const focusTags = {
  list: () => call<{ tags: FocusTagInfo[] }>("/focus-tags"),
};

export const prices = {
  status: () => call<{ statuses: PriceStatus[] }>("/prices/status"),
  get: (symbol: string, range: PriceRange) =>
    call<PriceComparison>(`/prices/${symbol}?range=${range}`),
};

export const review = {
  open: () => call<ReviewPage>("/review"),
  complete: (reviewId: string) =>
    call<CompleteReviewResponse>("/review/complete", {
      method: "POST",
      body: JSON.stringify({ review_id: reviewId }),
    }),
};

/**
 * Ask a bounded question about one company (D35).
 *
 * The answer is composed server-side from records already assessed. This client sends a
 * question and renders what comes back; it does not summarise, rephrase or fill gaps —
 * an "I don't have enough evidence" is the answer, not a case to paper over.
 */
export const explainer = {
  ask: (symbol: string, question: string) =>
    call<ExplainerAnswer>(`/companies/${symbol}/explain`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};

/**
 * The conversational assistant (D40).
 *
 * One call, into the system's own intelligence. `symbol` is UI context — the company the
 * reader is looking at — not part of the question, so "why did this fall?" needs no
 * ticker. Everything in the reply was decided by the deterministic core before this
 * client saw it.
 */
export const assistant = {
  ask: (question: string, symbol?: string) =>
    call<AssistantAnswer>("/assistant/ask", {
      method: "POST",
      body: JSON.stringify(symbol ? { question, symbol } : { question }),
    }),
};

/**
 * Levels the reader asked to be told about (D37).
 *
 * Set here, settled by the scheduled cycle against stored end-of-day closes, and surfaced
 * on the next visit. Nothing in this client decides whether a level was reached.
 */
export const watchPoints = {
  list: () => call<{ points: WatchPoint[] }>("/watch-points"),
  add: (symbol: string, level: number, note: string) =>
    call<WatchPoint>(`/companies/${symbol}/watch-points`, {
      method: "POST",
      body: JSON.stringify({ level, note }),
    }),
  acknowledge: (pointId: string) =>
    call<WatchPoint>(`/watch-points/${pointId}/acknowledge`, { method: "POST" }),
  remove: (pointId: string) =>
    call<RemovedResponse>(`/watch-points/${pointId}`, { method: "DELETE" }),
};

/** What this server is. Read once, so a client can label simulated data (D42). */
export const meta = {
  get: () => call<Meta>("/meta"),
};

/** Restore the judge scenario. Only exists when the server started in judge mode. */
export const judge = {
  reset: () => call<{ status: string }>("/judge/reset", { method: "POST" }),
};
