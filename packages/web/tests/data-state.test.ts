import { describe, expect, test } from "bun:test";
import { DATA_STATES, labelOf, toneOf, type DataState } from "../src/lib/data-state";

describe("data states", () => {
  test("every state has a label and a tone", () => {
    for (const state of DATA_STATES) {
      expect(labelOf(state)).toBeTruthy();
      expect(toneOf(state)).toBeTruthy();
    }
  });

  test("a conclusion and an admission are never the same state", () => {
    const conclusion: DataState = "no-meaningful-change";
    const admission: DataState = "unable-to-evaluate";

    expect(labelOf(conclusion)).not.toBe(labelOf(admission));
    expect(toneOf(conclusion)).toBe("settled");
    expect(toneOf(admission)).toBe("unknown");
  });
});
