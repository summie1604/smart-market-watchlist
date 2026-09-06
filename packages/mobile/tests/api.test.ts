import { afterEach, describe, expect, mock, test } from "bun:test";
import { createMobileApi } from "../src/api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("mobile API client", () => {
  test("uses the shared version prefix and bearer session", async () => {
    const fetchMock = mock(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ needs_attention: [] }), { status: 200 }),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await createMobileApi({
      baseUrl: "https://example.test",
      sessionToken: "session-1",
    }).openReview();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] ?? [undefined, undefined];
    expect(url).toBe("https://example.test/v1/review");
    expect((init as RequestInit).headers).toMatchObject({
      authorization: "Bearer session-1",
    });
  });

  test("completes the server-issued review by id, never by a client timestamp", async () => {
    const fetchMock = mock(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            checkpoint: "2026-09-06T00:00:00Z",
            outcome: "advanced",
          }),
          {
            status: 200,
          },
        ),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await createMobileApi({ baseUrl: "https://example.test" }).completeReview(
      "review-123",
    );

    const [url, init] = fetchMock.mock.calls[0] ?? [undefined, undefined];
    expect(url).toBe("https://example.test/v1/review/complete");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      review_id: "review-123",
    });
  });
});

describe("bounded explainer", () => {
  test("asks one company through the shared v1 contract", async () => {
    const fetchMock = mock(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(
          JSON.stringify({
            symbol: "RELIANCE",
            answered: true,
            statements: [],
            window: { basis: "since your last completed review" },
          }),
          { status: 200 },
        ),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await createMobileApi({ baseUrl: "https://example.test" }).explain(
      "RELIANCE",
      "What changed recently?",
    );

    const [url, init] = fetchMock.mock.calls[0] ?? [undefined, undefined];
    expect(url).toBe("https://example.test/v1/companies/RELIANCE/explain");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      question: "What changed recently?",
    });
  });
});
