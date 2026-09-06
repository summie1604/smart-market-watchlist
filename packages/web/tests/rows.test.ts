import { describe, expect, test } from "bun:test";
import {
  applyFocus,
  buildRows,
  byRecency,
  disputedBy,
  filterByCompany,
  groupByKind,
  isWeakSource,
  kindOf,
  byTime,
  demandingDevelopments,
  differingVerdicts,
  groupAttentionItems,
  groupedEvidence,
  needsAttention,
  outsideFocus,
  sortRows,
  rowBadge,
  whenText,
} from "../src/lib/rows";
import type {
  Assessment,
  AttentionItem,
  ReviewLine,
  ReviewPage,
  WatchedCompany,
} from "../src/lib/api";

function assessment(over: Partial<Assessment> = {}): Assessment {
  return {
    event_id: "e1",
    symbol: "RELIANCE",
    company: "Reliance Industries",
    event_type: "Agreements",
    description: "Something happened",
    occurred_at: "2026-09-05T10:00:00+00:00",
    attention: "MEDIUM",
    confidence: "MEDIUM",
    score: 3,
    scoring_version: "v",
    reasons: [],
    coverage: { complete: true, note: "", records: [] },
    corroboration: {
      article_count: 1,
      independent_source_count: 1,
      summary: "1 article · 1 independent source",
      has_authoritative: false,
    },
    evidence: [],
    contradiction: { state: "STANDING", disputed_by: null, detail: "", confirmed: false },
    source_standing: "ESTABLISHED",
    source_standing_label: "established outlet",
    focus: [],
    ...over,
  };
}

function item(
  over: Partial<Assessment> = {},
  symbol = "RELIANCE",
  development?: string,
): AttentionItem {
  const built = assessment({ symbol, ...over });
  return {
    symbol,
    company: `${symbol} Ltd`,
    assessment: built,
    // The backend decides this; the client only groups by it.
    development_id: development ?? built.event_id,
    development_sources: built.corroboration.independent_source_count,
  };
}

function line(over: Partial<ReviewLine> = {}): ReviewLine {
  return {
    symbol: "RELIANCE",
    company: "Reliance Industries",
    coverage_tier: "FULL",
    state: "changed",
    detail: "1 assessed change.",
    assessments: [],
    ...over,
  };
}

function page(over: Partial<ReviewPage> = {}): ReviewPage {
  return {
    review_id: "r",
    previous_checkpoint: null,
    review_cutoff: "2026-09-05T12:00:00+00:00",
    attention_count: 0,
    needs_attention: [],
    triggered_watch_points: [],
    changed: [],
    newly_added: [],
    unable: [],
    quiet: [],
    ...over,
  };
}

/** Index access is optional under `noUncheckedIndexedAccess`; assert once, here. */
function only<T>(items: T[], index = 0): T {
  const item = items[index];
  if (item === undefined) throw new Error(`expected an item at ${index}`);
  return item;
}

const watched = (symbol: string): WatchedCompany => ({
  symbol,
  company: `${symbol} Ltd`,
  coverage_tier: "FULL",
  added_at: "2026-09-01T00:00:00+00:00",
  watched_from: "2026-09-01T00:00:00+00:00",
  sector_index: "^NSEI",
  sector_label: "NIFTY 50",
  reason: "",
  watch_for: "",
  tags: [],
});

describe("watchlist rows", () => {
  test("a quiet company still shows the latest thing we know", () => {
    const older = assessment({ event_id: "old", occurred_at: "2026-09-01T09:00:00+00:00" });
    const newer = assessment({ event_id: "new", occurred_at: "2026-09-04T09:00:00+00:00" });

    const row = only(
      buildRows(
        [watched("RELIANCE")],
        page({ quiet: [line({ state: "quiet", detail: "No meaningful change." })] }),
        [older, newer],
      ),
    );

    expect(row.state).toBe("quiet");
    expect(row.headline).toBeNull();
    expect(row.latest?.event_id).toBe("new");
    expect(row.history).toHaveLength(2);
  });

  test("the row leads with the engine's first in-window assessment, not our own pick", () => {
    const first = assessment({ event_id: "ranked-first", attention: "HIGH" });
    const second = assessment({ event_id: "ranked-second", attention: "LOW" });

    const row = only(
      buildRows(
        [watched("RELIANCE")],
        page({ changed: [line({ assessments: [first, second] })] }),
        [second, first],
      ),
    );

    expect(row.headline?.event_id).toBe("ranked-first");
    expect(row.newCount).toBe(2);
  });

  test("only this company's history reaches its row", () => {
    const mine = assessment({ symbol: "RELIANCE", event_id: "mine" });
    const theirs = assessment({ symbol: "INFY", event_id: "theirs" });

    const row = only(
      buildRows([watched("RELIANCE")], page({ quiet: [line({ state: "quiet" })] }), [mine, theirs]),
    );

    expect(row.history.map((a) => a.event_id)).toEqual(["mine"]);
  });

  test("a high-attention development outranks a low one on an older company", () => {
    const rows = buildRows(
      [watched("OLD"), watched("FRESH")],
      page({
        changed: [
          line({ symbol: "OLD", assessments: [assessment({ symbol: "OLD", attention: "LOW" })] }),
        ],
        newly_added: [
          line({
            symbol: "FRESH",
            state: "new",
            assessments: [assessment({ symbol: "FRESH", attention: "HIGH" })],
          }),
        ],
      }),
      [],
    );

    expect(rows.map((r) => r.symbol)).toEqual(["FRESH", "OLD"]);
  });

  test("companies asking for something sort above quiet ones", () => {
    const rows = buildRows(
      [watched("AAA"), watched("BBB")],
      page({
        quiet: [line({ symbol: "AAA", state: "quiet" })],
        changed: [
          line({ symbol: "BBB", assessments: [assessment({ symbol: "BBB", attention: "HIGH" })] }),
        ],
      }),
      [],
    );

    expect(rows.map((r) => r.symbol)).toEqual(["BBB", "AAA"]);
  });

  test("badges copy the engine's verdict rather than deriving one", () => {
    const changed = only(
      buildRows(
        [watched("RELIANCE")],
        page({ changed: [line({ assessments: [assessment({ attention: "HIGH" })] })] }),
        [],
      ),
    );
    const quiet = only(
      buildRows([watched("RELIANCE")], page({ quiet: [line({ state: "quiet" })] }), []),
    );
    const unable = only(
      buildRows([watched("RELIANCE")], page({ unable: [line({ state: "unable" })] }), []),
    );

    expect(rowBadge(changed).tone).toBe("HIGH");
    expect(rowBadge(quiet).tone).toBe("QUIET");
    expect(rowBadge(unable).tone).toBe("UNABLE_TO_EVALUATE_RELIABLY");
  });
});

describe("needs attention", () => {
  test("renders exactly what the backend served, in the order it arrived", () => {
    const served = [
      item({ event_id: "high", attention: "HIGH" }),
      item({ event_id: "medium", attention: "MEDIUM" }),
      item({ event_id: "low", attention: "LOW" }),
    ];

    const items = needsAttention(page({ needs_attention: served }));

    expect(items.map((i) => i.assessment.event_id)).toEqual(["high", "medium", "low"]);
  });

  test("is empty when nothing is new, so the view can say so plainly", () => {
    expect(needsAttention(page({ quiet: [line({ state: "quiet" })] }))).toEqual([]);
  });

  test("does not re-sort what it was given", () => {
    // Deliberately out of severity order: if this module re-ranked, it would reorder.
    const served = [
      item({ event_id: "a", attention: "MEDIUM" }),
      item({ event_id: "b", attention: "HIGH" }),
    ];

    expect(
      needsAttention(page({ needs_attention: served })).map((i) => i.assessment.event_id),
    ).toEqual(["a", "b"]);
  });
});

describe("filtering by company", () => {
  const items = [
    item({ event_id: "r1" }, "RELIANCE"),
    item({ event_id: "i1" }, "INFY"),
    item({ event_id: "r2" }, "RELIANCE"),
  ];

  test("narrows to one company", () => {
    expect(filterByCompany(items, "RELIANCE").map((i) => i.assessment.event_id)).toEqual([
      "r1",
      "r2",
    ]);
  });

  test("no selection leaves everything untouched", () => {
    expect(filterByCompany(items, null)).toEqual(items);
  });

  test("narrowing never reorders", () => {
    const mixed = [
      item({ event_id: "medium", attention: "MEDIUM" }, "INFY"),
      item({ event_id: "high", attention: "HIGH" }, "INFY"),
    ];

    expect(filterByCompany(mixed, "INFY").map((i) => i.assessment.event_id)).toEqual([
      "medium",
      "high",
    ]);
  });

  test("a company with nothing new filters to empty rather than to everything", () => {
    expect(filterByCompany(items, "TCS")).toEqual([]);
  });
});

describe("focus", () => {
  const earnings = [{ tag: "earnings", label: "Earnings and results", why: "reports results" }];

  test("with no focus selected nothing is narrowed and nothing is marked", () => {
    const items = [item({ event_id: "a", attention: "LOW" })];

    const result = applyFocus(items, []);

    expect(result.visible).toEqual(items);
    expect(result.narrowed).toBe(0);
    expect(outsideFocus(items[0]!.assessment, [])).toBe(false);
  });

  test("a matching item stays, and its match came from the backend", () => {
    const matching = item({ event_id: "match", attention: "LOW", focus: earnings });

    const result = applyFocus([matching], ["earnings"]);

    expect(result.visible.map((i) => i.assessment.event_id)).toEqual(["match"]);
    expect(result.narrowed).toBe(0);
  });

  test("a LOW outside the focus is narrowed away, and the count is reported", () => {
    const result = applyFocus([item({ event_id: "low", attention: "LOW" })], ["earnings"]);

    expect(result.visible).toEqual([]);
    expect(result.narrowed).toBe(1);
  });

  test("a HIGH outside the focus is never hidden", () => {
    const result = applyFocus([item({ event_id: "high", attention: "HIGH" })], ["earnings"]);

    expect(result.visible.map((i) => i.assessment.event_id)).toEqual(["high"]);
    expect(result.keptAnyway).toBe(1);
    expect(result.narrowed).toBe(0);
    expect(outsideFocus(result.visible[0]!.assessment, ["earnings"])).toBe(true);
  });

  test("selecting several tags matches any of them", () => {
    const result = applyFocus(
      [item({ event_id: "e", attention: "MEDIUM", focus: earnings })],
      ["regulation", "earnings"],
    );

    expect(result.visible).toHaveLength(1);
  });

  test("focus narrows without reordering what survives", () => {
    const items = [
      item({ event_id: "keep-1", attention: "MEDIUM", focus: earnings }),
      item({ event_id: "drop", attention: "LOW" }),
      item({ event_id: "keep-2", attention: "LOW", focus: earnings }),
    ];

    const result = applyFocus(items, ["earnings"]);

    expect(result.visible.map((i) => i.assessment.event_id)).toEqual(["keep-1", "keep-2"]);
  });
});

describe("contradictions", () => {
  const denial = assessment({
    event_id: "denial",
    description: "The company denies it signed any agreement",
  });
  const disputed = assessment({
    event_id: "claim",
    contradiction: {
      state: "DISPUTED",
      disputed_by: "denial",
      detail: 'Reuters reports this being denied. Grounded in: "denies".',
      confirmed: true,
    },
  });

  test("the disputing record is resolved from the link the backend issued", () => {
    expect(disputedBy(disputed, [disputed, denial])?.event_id).toBe("denial");
  });

  test("a standing event links to nothing", () => {
    expect(disputedBy(assessment(), [disputed, denial])).toBeNull();
  });

  test("a link we do not hold resolves to nothing rather than to the wrong record", () => {
    expect(disputedBy(disputed, [disputed])).toBeNull();
  });

  test("an unconfirmed relationship keeps its link and is not a contradiction", () => {
    const possible = assessment({
      event_id: "possible",
      contradiction: {
        state: "STANDING",
        disputed_by: "denial",
        detail: "Possibly related; relationship not confirmed (a less authoritative source).",
        confirmed: false,
      },
    });

    expect(possible.contradiction.confirmed).toBe(false);
    expect(disputedBy(possible, [possible, denial])?.event_id).toBe("denial");
  });
});

describe("formatting", () => {
  test("recency sorts newest first", () => {
    const sorted = byRecency([
      assessment({ event_id: "old", occurred_at: "2026-09-01T00:00:00+00:00" }),
      assessment({ event_id: "new", occurred_at: "2026-09-05T00:00:00+00:00" }),
    ]);
    expect(sorted.map((a) => a.event_id)).toEqual(["new", "old"]);
  });

  test("missing timestamps render as a dash rather than Invalid Date", () => {
    expect(whenText(undefined)).toBe("—");
  });
});

describe("grouping by kind", () => {
  const withEvidence = (source: string, over: Partial<Assessment> = {}) =>
    assessment({
      ...over,
      evidence: [
        {
          source,
          ref: `${source}-${over.event_id ?? "e"}`,
          tier: "CREDIBLE_REPORTING",
          publisher: "P",
          subject_company: "Reliance Industries",
          published_at: "2026-09-05T10:00:00+00:00",
          url: "",
          standing: "ESTABLISHED",
          standing_label: "established outlet",
        },
      ],
    });

  test("a filing is a disclosure even when news covers the same thing", () => {
    const filed = assessment({
      event_id: "filed",
      evidence: [
        {
          source: "news",
          ref: "n",
          tier: "CREDIBLE_REPORTING",
          publisher: "Reuters",
          subject_company: "R",
          published_at: "x",
          url: "",
          standing: "ESTABLISHED",
          standing_label: "established outlet",
        },
        {
          source: "nse-disclosures",
          ref: "f",
          tier: "OFFICIAL_DISCLOSURE",
          publisher: "NSE",
          subject_company: "R",
          published_at: "x",
          url: "",
          standing: "OFFICIAL",
          standing_label: "exchange filing",
        },
      ],
    });

    expect(kindOf(filed)).toBe("disclosure");
  });

  test("developments are split into disclosures, market and news", () => {
    const groups = groupByKind([
      withEvidence("news", { event_id: "n1", event_type: "Agreements" }),
      withEvidence("nse-disclosures", { event_id: "d1", event_type: "Outcome of Board Meeting" }),
      withEvidence("market", { event_id: "m1", event_type: "Unusual price movement" }),
    ]);

    expect(groups.map((g) => g.kind)).toEqual(["disclosure", "market", "news"]);
    expect(groups.every((g) => g.count === 1)).toBe(true);
  });

  test("news is split again by event type, busiest first", () => {
    const groups = groupByKind([
      withEvidence("news", { event_id: "a", event_type: "Agreements" }),
      withEvidence("news", { event_id: "b", event_type: "Product Launch" }),
      withEvidence("news", { event_id: "c", event_type: "Product Launch" }),
    ]);

    const news = groups.find((g) => g.kind === "news");
    expect(news?.sections.map((s) => `${s.type}:${s.assessments.length}`)).toEqual([
      "Product Launch:2",
      "Agreements:1",
    ]);
  });

  test("empty kinds are left out rather than rendered as empty headings", () => {
    const groups = groupByKind([withEvidence("news", { event_id: "only" })]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.kind).toBe("news");
  });

  test("grouping preserves the order it was given inside a section", () => {
    const groups = groupByKind([
      withEvidence("news", { event_id: "first", event_type: "Agreements" }),
      withEvidence("news", { event_id: "second", event_type: "Agreements" }),
    ]);

    expect(groups[0]?.sections[0]?.assessments.map((a) => a.event_id)).toEqual([
      "first",
      "second",
    ]);
  });
});

describe("source standing", () => {
  test("a weak source is worth calling out on a compact row", () => {
    expect(isWeakSource("UNRECOGNISED")).toBe(true);
    expect(isWeakSource("SYNDICATED_RELEASE")).toBe(true);
  });

  test("a recognised source needs no warning beside it", () => {
    expect(isWeakSource("OFFICIAL")).toBe(false);
    expect(isWeakSource("ESTABLISHED")).toBe(false);
    expect(isWeakSource("COMPUTED")).toBe(false);
  });

  test("standing is read from the backend, never derived from the publisher here", () => {
    // The client is given the decision. If it recomputed one from the publisher string,
    // two clients could disagree about the same report.
    const unrecognised = assessment({
      source_standing: "UNRECOGNISED",
      source_standing_label: "unrecognised publisher",
      evidence: [
        {
          source: "news",
          ref: "x",
          tier: "CREDIBLE_REPORTING",
          publisher: "Reuters",
          subject_company: "R",
          published_at: "x",
          url: "",
          standing: "UNRECOGNISED",
          standing_label: "unrecognised publisher",
        },
      ],
    });

    expect(unrecognised.source_standing).toBe("UNRECOGNISED");
    expect(isWeakSource(unrecognised.source_standing)).toBe(true);
  });
});

describe("the card's stored trace", () => {
  // The sparkline maps a pointer position to the *nearest stored session*, never to a
  // value between two of them — there is no such session, and inventing one would be a
  // fabricated price wearing a chart's authority.
  const nearest = (ratio: number, count: number) =>
    Math.min(Math.max(Math.round(ratio * (count - 1)), 0), count - 1);

  test("a position lands on a session that exists", () => {
    expect(nearest(0, 14)).toBe(0);
    expect(nearest(1, 14)).toBe(13);
    expect(nearest(0.5, 14)).toBe(7);
  });

  test("a position outside the trace is clamped rather than extrapolated", () => {
    expect(nearest(-0.4, 14)).toBe(0);
    expect(nearest(1.9, 14)).toBe(13);
  });

  test("every index it can produce is a real session", () => {
    const sessions = Array.from({ length: 14 }, (_, i) => i);
    for (let step = -5; step <= 15; step += 1) {
      expect(sessions[nearest(step / 10, sessions.length)]).toBeDefined();
    }
  });
});

describe("watchlist sorting", () => {
  // A presentation axis over companies (D38). It must never look like the canonical
  // ordering of developments, which the backend owns.
  const rows = () =>
    buildRows(
      [
        { ...watched("AAA"), added_at: "2026-09-01T00:00:00+00:00" },
        { ...watched("ZZZ"), added_at: "2026-09-05T00:00:00+00:00" },
        { ...watched("MMM"), added_at: "2026-09-03T00:00:00+00:00" },
      ],
      page({
        quiet: [
          line({ symbol: "AAA", state: "quiet" }),
          line({ symbol: "ZZZ", state: "quiet" }),
          line({ symbol: "MMM", state: "quiet" }),
        ],
      }),
      [],
    );

  const changes: Record<string, number | null> = { AAA: -3.2, ZZZ: 1.4, MMM: null };
  const changeFor = (symbol: string) => changes[symbol];
  const order = (mode: Parameters<typeof sortRows>[2]) =>
    sortRows(rows(), changeFor, mode).map((r) => r.symbol);

  test("the default leaves the backend's own arrangement untouched", () => {
    expect(order("attention")).toEqual(rows().map((r) => r.symbol));
  });

  test("gainers lead, losers trail", () => {
    expect(order("gainers")).toEqual(["ZZZ", "AAA", "MMM"]);
    expect(order("losers")).toEqual(["AAA", "ZZZ", "MMM"]);
  });

  test("largest move ignores direction", () => {
    expect(order("movement")).toEqual(["AAA", "ZZZ", "MMM"]);
  });

  test("a company with no stored price sorts last, not as a flat move", () => {
    // MMM is missing, not unchanged. Placing it mid-list would assert it did not move.
    for (const mode of ["gainers", "losers", "movement"] as const) {
      expect(order(mode).at(-1)).toBe("MMM");
    }
  });

  test("alphabetical and recently added need no price at all", () => {
    expect(order("alphabetical")).toEqual(["AAA", "MMM", "ZZZ"]);
    expect(order("recent")).toEqual(["ZZZ", "MMM", "AAA"]);
  });

  test("sorting never changes what a row contains", () => {
    const before = rows().find((r) => r.symbol === "AAA");
    const after = sortRows(rows(), changeFor, "losers").find((r) => r.symbol === "AAA");
    expect(after).toEqual(before!);
  });
});

describe("company timeline", () => {
  const at = (id: string, when: string, source: string) =>
    assessment({
      event_id: id,
      occurred_at: when,
      evidence: [
        {
          source,
          ref: id,
          tier: "CREDIBLE_REPORTING",
          publisher: "P",
          subject_company: "R",
          published_at: when,
          url: "",
          standing: "ESTABLISHED",
          standing_label: "established outlet",
        },
      ],
    });

  test("reads newest first, across kinds", () => {
    const entries = byTime([
      at("news", "2026-09-05T11:15:00+00:00", "news"),
      at("move", "2026-09-05T10:30:00+00:00", "market"),
      at("filing", "2026-09-05T10:47:00+00:00", "nse-disclosures"),
    ]);

    expect(entries.map((e) => e.assessment.event_id)).toEqual(["news", "filing", "move"]);
    expect(entries.map((e) => e.kind)).toEqual(["news", "disclosure", "market"]);
  });

  test("carries a readable label for each entry's kind", () => {
    expect(byTime([at("m", "2026-09-05T10:30:00+00:00", "market")])[0]?.label).toBe(
      "Market observations",
    );
  });

  test("an empty record produces an empty timeline rather than a placeholder", () => {
    expect(byTime([])).toEqual([]);
  });
});

describe("grouping attention items", () => {
  // Which records belong together is decided server-side (D43). These tests pin that the
  // client groups by that key faithfully and changes nothing else.
  test("records sharing a development collapse into one group", () => {
    const groups = groupAttentionItems([
      item({ event_id: "primary" }, "RELIANCE", "dev-1"),
      item({ event_id: "second" }, "RELIANCE", "dev-1"),
      item({ event_id: "third" }, "RELIANCE", "dev-1"),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]!.primary.assessment.event_id).toBe("primary");
    expect(groups[0]!.related.map((r) => r.assessment.event_id)).toEqual(["second", "third"]);
  });

  test("the first item in canonical order becomes the primary", () => {
    // Order in equals order out: grouping must not re-rank anything.
    const groups = groupAttentionItems([
      item({ event_id: "first" }, "RELIANCE", "dev-1"),
      item({ event_id: "later" }, "RELIANCE", "dev-1"),
    ]);

    expect(groups[0]!.primary.assessment.event_id).toBe("first");
  });

  test("separate developments stay separate and keep their order", () => {
    const groups = groupAttentionItems([
      item({ event_id: "a" }, "RELIANCE", "dev-1"),
      item({ event_id: "b" }, "INFY", "dev-2"),
      item({ event_id: "c" }, "RELIANCE", "dev-1"),
    ]);

    expect(groups.map((g) => g.developmentId)).toEqual(["dev-1", "dev-2"]);
  });

  test("an ungrouped item is a group of one", () => {
    const groups = groupAttentionItems([item({ event_id: "solo" })]);

    expect(groups).toHaveLength(1);
    expect(groups[0]!.related).toEqual([]);
  });

  test("evidence is deduplicated for display only", () => {
    const shared = {
      source: "news",
      ref: "same-article",
      tier: "CREDIBLE_REPORTING",
      publisher: "Reuters",
      subject_company: "R",
      published_at: "x",
      url: "",
      standing: "ESTABLISHED" as const,
      standing_label: "established outlet",
    };
    const groups = groupAttentionItems([
      item({ event_id: "a", evidence: [shared] }, "RELIANCE", "dev-1"),
      item({ event_id: "b", evidence: [shared] }, "RELIANCE", "dev-1"),
    ]);

    expect(groupedEvidence(groups[0]!)).toHaveLength(1);
    // The records themselves are untouched.
    expect(groups[0]!.primary.assessment.evidence).toHaveLength(1);
    expect(groups[0]!.related[0]!.assessment.evidence).toHaveLength(1);
  });

  test("a differing verdict inside a development is surfaced, not hidden", () => {
    const groups = groupAttentionItems([
      item({ event_id: "now", attention: "HIGH" }, "RELIANCE", "dev-1"),
      item({ event_id: "earlier", attention: "MEDIUM" }, "RELIANCE", "dev-1"),
    ]);

    expect(differingVerdicts(groups[0]!)).toBe(true);
  });

  test("a development whose records agree needs no history note", () => {
    const groups = groupAttentionItems([
      item({ event_id: "a", attention: "HIGH" }, "RELIANCE", "dev-1"),
      item({ event_id: "b", attention: "HIGH" }, "RELIANCE", "dev-1"),
    ]);

    expect(differingVerdicts(groups[0]!)).toBe(false);
  });

  test("grouping never invents a relationship the server did not assign", () => {
    const groups = groupAttentionItems([
      item({ event_id: "a", description: "Identical wording" }, "RELIANCE", "dev-1"),
      item({ event_id: "b", description: "Identical wording" }, "RELIANCE", "dev-2"),
    ]);

    expect(groups).toHaveLength(2);
  });
});

describe("the hero's attention previews", () => {
  // The hero must be a shorter view of one answer, never a second selection rule.
  test("previews only the levels that ask something of a reader", () => {
    const groups = demandingDevelopments([
      item({ event_id: "high", attention: "HIGH" }, "RELIANCE", "d1"),
      item({ event_id: "medium", attention: "MEDIUM" }, "TCS", "d2"),
      item({ event_id: "low", attention: "LOW" }, "INFY", "d3"),
    ]);

    expect(groups.map((g) => g.primary.assessment.event_id)).toEqual(["high", "medium"]);
  });

  test("it preserves canonical order rather than re-ranking", () => {
    // Deliberately given MEDIUM before HIGH: re-ranking here would reorder them.
    const groups = demandingDevelopments([
      item({ event_id: "first", attention: "MEDIUM" }, "TCS", "d1"),
      item({ event_id: "second", attention: "HIGH" }, "RELIANCE", "d2"),
    ]);

    expect(groups.map((g) => g.primary.assessment.event_id)).toEqual(["first", "second"]);
  });

  test("a grouped development is previewed once", () => {
    const groups = demandingDevelopments([
      item({ event_id: "a", attention: "HIGH" }, "RELIANCE", "d1"),
      item({ event_id: "b", attention: "HIGH" }, "RELIANCE", "d1"),
      item({ event_id: "c", attention: "HIGH" }, "RELIANCE", "d1"),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]!.related).toHaveLength(2);
  });

  test("nothing demanding produces no previews rather than an invented one", () => {
    expect(demandingDevelopments([])).toEqual([]);
    expect(demandingDevelopments([item({ attention: "LOW" })])).toEqual([]);
  });
});
