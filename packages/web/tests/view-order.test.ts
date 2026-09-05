import { describe, expect, test } from "bun:test";
import {
  applyViewSort,
  attentionLabel,
  type Assessment,
  type Confidence,
} from "../src/lib/api";

function stub(
  symbol: string,
  confidence: Confidence = "HIGH",
  occurred_at = "2026-09-05T00:00:00+00:00",
): Assessment {
  return {
    event_id: `id-${symbol}`,
    symbol,
    company: symbol,
    event_type: "Agreements",
    description: "",
    occurred_at,
    attention: "MEDIUM",
    confidence,
    score: 3,
    scoring_version: "test",
    reasons: [],
    coverage: { complete: true, note: "", records: [] },
    evidence: [],
  };
}

describe("view sorting", () => {
  test("with no reader-selected sort, the backend's order is rendered unchanged", () => {
    // The engine ranks; the client must not re-derive that answer.
    const fromApi = [stub("ZEE"), stub("ADANI"), stub("MARUTI")];

    const rendered = applyViewSort(fromApi, null);

    expect(rendered.map((a) => a.symbol)).toEqual(["ZEE", "ADANI", "MARUTI"]);
  });

  test("a reader-selected sort reorders without mutating the source list", () => {
    const fromApi = [stub("ZEE"), stub("ADANI")];

    const rendered = applyViewSort(fromApi, "company");

    expect(rendered.map((a) => a.symbol)).toEqual(["ADANI", "ZEE"]);
    expect(fromApi.map((a) => a.symbol)).toEqual(["ZEE", "ADANI"]);
  });

  test("confidence sort orders by certainty, not by score", () => {
    const fromApi = [stub("A", "LOW"), stub("B", "HIGH"), stub("C", "MEDIUM")];

    const rendered = applyViewSort(fromApi, "confidence");

    expect(rendered.map((a) => a.symbol)).toEqual(["B", "C", "A"]);
  });
});

describe("attention labels", () => {
  test("a conclusion and an admission never read alike", () => {
    expect(attentionLabel("NO_MEANINGFUL_CHANGE")).toBe("No meaningful change");
    expect(attentionLabel("UNABLE_TO_EVALUATE_RELIABLY")).toBe("Unable to evaluate reliably");
    expect(attentionLabel("NO_MEANINGFUL_CHANGE")).not.toBe(
      attentionLabel("UNABLE_TO_EVALUATE_RELIABLY"),
    );
  });

  test("ranked levels read as a request for attention", () => {
    expect(attentionLabel("HIGH")).toBe("HIGH attention");
    expect(attentionLabel("LOW")).toBe("LOW attention");
  });
});
