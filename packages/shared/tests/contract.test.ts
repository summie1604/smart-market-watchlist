import { describe, expect, test } from "bun:test";
import { API_PREFIX, API_VERSION } from "../src";

describe("shared API contract", () => {
  test("the prefix and advertised version cannot drift apart", () => {
    expect(API_PREFIX).toBe(`/${API_VERSION}`);
  });
});
