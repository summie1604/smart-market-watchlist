import {
  API_PREFIX,
  type CompleteReviewResponse,
  type ExplainerAnswerView,
  type WatchPointView,
  type ReviewPageView,
} from "@smart-market-watchlist/shared";

export interface MobileApi {
  openReview(): Promise<ReviewPageView>;
  completeReview(reviewId: string): Promise<CompleteReviewResponse>;
  /** Ask a bounded question about one company (D35). Answered from stored records. */
  explain(symbol: string, question: string): Promise<ExplainerAnswerView>;
  /** Mark a triggered watch point as seen, so it stops asking (D37). */
  acknowledgeWatchPoint(pointId: string): Promise<WatchPointView>;
}

interface MobileApiOptions {
  baseUrl: string;
  sessionToken?: string;
}

export function createMobileApi(options: MobileApiOptions): MobileApi {
  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const response = await fetch(`${options.baseUrl}${API_PREFIX}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(options.sessionToken
          ? { authorization: `Bearer ${options.sessionToken}` }
          : {}),
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        detail?: unknown;
      };
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : `Request failed (${response.status})`,
      );
    }
    return (await response.json()) as T;
  };

  return {
    openReview: () => request<ReviewPageView>("/review"),
    completeReview: (reviewId) =>
      request<CompleteReviewResponse>("/review/complete", {
        method: "POST",
        body: JSON.stringify({ review_id: reviewId }),
      }),
    acknowledgeWatchPoint: (pointId) =>
      request<WatchPointView>(`/watch-points/${pointId}/acknowledge`, {
        method: "POST",
      }),
    explain: (symbol, question) =>
      request<ExplainerAnswerView>(`/companies/${symbol}/explain`, {
        method: "POST",
        body: JSON.stringify({ question }),
      }),
  };
}
