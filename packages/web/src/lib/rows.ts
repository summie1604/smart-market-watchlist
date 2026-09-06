/**
 * Turning what the backend returned into what a row shows.
 *
 * Selection and formatting only. Nothing here scores, ranks or re-judges: the engine's
 * order is read as given, its verdicts are copied verbatim, and the one ordering decision
 * made locally — which development is the *latest* for a company — is a question about
 * recency, not about attention.
 */

import type { AttentionItem, Assessment, ReviewPage, WatchedCompany } from "./api";

export type RowState = "changed" | "new" | "unable" | "quiet";

export interface CompanyRow {
  symbol: string;
  company: string;
  coverageTier: string;
  state: RowState;
  /** What the review says about this company, in its own words. */
  detail: string;
  /** Highest-ranked assessment inside the review window, if any. */
  headline: Assessment | null;
  /** Most recent assessment we hold at all — shown when nothing is new. */
  latest: Assessment | null;
  /** Everything we hold for this company, newest first. */
  history: Assessment[];
  newCount: number;
  /** When this reader added the company — the only input "recently added" sorting needs. */
  addedAt: string;
}

const STATE_ORDER: Record<RowState, number> = { changed: 0, new: 1, unable: 2, quiet: 3 };
const ATTENTION_ORDER: Record<string, number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
  UNABLE_TO_EVALUATE_RELIABLY: 3,
  NO_MEANINGFUL_CHANGE: 4,
};

/** Newest first, by when the development happened. */
export function byRecency(assessments: Assessment[]): Assessment[] {
  return [...assessments].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
}

export function buildRows(
  companies: WatchedCompany[],
  review: ReviewPage,
  everything: Assessment[],
): CompanyRow[] {
  const lines = [
    ...review.changed.map((l) => ({ line: l, state: "changed" as RowState })),
    ...review.newly_added.map((l) => ({ line: l, state: "new" as RowState })),
    ...review.unable.map((l) => ({ line: l, state: "unable" as RowState })),
    ...review.quiet.map((l) => ({ line: l, state: "quiet" as RowState })),
  ];

  const rows = companies.map((company) => {
    const entry = lines.find((l) => l.line.symbol === company.symbol);
    // The engine ranked the assessments on this line; the first is its answer, not ours.
    const inWindow = entry?.line.assessments ?? [];
    const history = byRecency(everything.filter((a) => a.symbol === company.symbol));

    return {
      symbol: company.symbol,
      company: company.company,
      coverageTier: company.coverage_tier,
      state: entry?.state ?? "quiet",
      detail: entry?.line.detail ?? "",
      headline: inWindow[0] ?? null,
      latest: history[0] ?? null,
      history,
      newCount: inWindow.length,
      addedAt: company.added_at,
    };
  });

  // Attention leads, because that is what the board is for: a HIGH development should not
  // rank below a LOW one merely because the company was added more recently. State breaks
  // ties among rows with nothing new. This orders *rows* using the engine's own verdicts;
  // it never changes one.
  const attentionRank = (row: CompanyRow) =>
    row.headline ? (ATTENTION_ORDER[row.headline.attention] ?? 9) : 9;

  return rows.sort(
    (a, b) =>
      attentionRank(a) - attentionRank(b) ||
      STATE_ORDER[a.state] - STATE_ORDER[b.state] ||
      a.symbol.localeCompare(b.symbol),
  );
}

/**
 * What is new since the last completed review.
 *
 * A pass-through. The backend serves this flat and already ordered by severity and then
 * recency; re-deriving the order here from the per-company sections would be a second
 * answer to a product question (D26).
 */
export function needsAttention(review: ReviewPage): AttentionItem[] {
  return review.needs_attention;
}

/* --- narrowing: by company, and by what the reader said they watch for -------- */

/** Show one company's items. Narrowing only — the order is untouched. */
export function filterByCompany<T extends { symbol: string }>(
  items: T[],
  symbol: string | null,
): T[] {
  return symbol === null ? items : items.filter((item) => item.symbol === symbol);
}

/**
 * Whether an item falls outside the focus the reader selected.
 *
 * Read from the backend's own `focus` annotation. The frontend never decides what
 * matches a tag — it only asks whether the annotation it was given includes one of the
 * tags currently switched on (D27).
 */
export function outsideFocus(assessment: Assessment, active: string[]): boolean {
  if (active.length === 0) return false;
  return !assessment.focus.some((match) => active.includes(match.tag));
}

export interface FocusResult<T> {
  visible: T[];
  /** HIGH items kept in view even though they fall outside the selected focus. */
  keptAnyway: number;
  /** Lower-severity items the focus narrowed away. Always stated, never silent. */
  narrowed: number;
}

/**
 * Apply the focus filter.
 *
 * **A HIGH is never hidden.** It stays, marked as being outside the stated focus,
 * because hiding it would be the product failing at the one job it claims in the name of
 * a preference the reader expressed before the evidence existed (D27). LOW and MEDIUM
 * are narrowed, and the count of what was narrowed away is returned so the interface can
 * say so rather than quietly showing less.
 */
export function applyFocus(
  items: AttentionItem[],
  active: string[],
): FocusResult<AttentionItem> {
  if (active.length === 0) return { visible: items, keptAnyway: 0, narrowed: 0 };

  const visible: AttentionItem[] = [];
  let keptAnyway = 0;
  let narrowed = 0;

  for (const item of items) {
    const outside = outsideFocus(item.assessment, active);
    if (!outside) {
      visible.push(item);
      continue;
    }
    if (item.assessment.attention === "HIGH") {
      visible.push(item);
      keptAnyway += 1;
      continue;
    }
    narrowed += 1;
  }
  return { visible, keptAnyway, narrowed };
}

/**
 * The record disputing this one, if we hold it.
 *
 * A lookup of a link the backend issued, not a judgement: which events contradict which
 * is decided by the gates in `core/contradiction.py` and arrives already decided (D29).
 */
export function disputedBy(
  assessment: Assessment,
  known: Assessment[],
): Assessment | null {
  const id = assessment.contradiction.disputed_by;
  if (id === null) return null;
  return known.find((a) => a.event_id === id) ?? null;
}

/** The badge a row wears. Copied from the engine, never computed here. */
export function rowBadge(row: CompanyRow): { label: string; tone: string } {
  if (row.headline) {
    return { label: `${row.headline.attention.replace(/_/g, " ").toLowerCase()}`, tone: row.headline.attention };
  }
  if (row.state === "unable") return { label: "can't evaluate", tone: "UNABLE_TO_EVALUATE_RELIABLY" };
  if (row.state === "new") return { label: "just added", tone: "NEW" };
  return { label: "quiet", tone: "QUIET" };
}

export function whenText(iso: string | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 8 ? `${days}d ago` : then.toLocaleDateString(undefined, { dateStyle: "medium" });
}


/* --- grouping developments by what kind of thing they are ------------------- */

export type Kind = "disclosure" | "market" | "news";

export interface KindGroup {
  kind: Kind;
  label: string;
  /** Developments of this kind, split further by the engine's own event type. */
  sections: { type: string; assessments: Assessment[] }[];
  count: number;
}

const KIND_LABEL: Record<Kind, string> = {
  disclosure: "Exchange disclosures",
  market: "Market observations",
  news: "News",
};

/** Where a development came from, decided by its evidence rather than by its wording. */
export function kindOf(assessment: Assessment): Kind {
  const sources = new Set(assessment.evidence.map((e) => e.source));
  if (sources.has("nse-disclosures")) return "disclosure";
  if (sources.has("market")) return "market";
  return "news";
}

/**
 * Split a company's record into disclosures, market observations and news, and split the
 * news again by event type.
 *
 * A filing and a rumour are different kinds of thing and reading them in one undifferentiated
 * stream is what makes a long record unreadable. Grouping is presentational: order within a
 * group stays newest-first, and nothing is reclassified — the kind comes from the evidence
 * and the type from the engine.
 */
export function groupByKind(assessments: Assessment[]): KindGroup[] {
  const order: Kind[] = ["disclosure", "market", "news"];
  return order
    .map((kind) => {
      const mine = assessments.filter((a) => kindOf(a) === kind);
      const types = new Map<string, Assessment[]>();
      for (const a of mine) {
        const bucket = types.get(a.event_type) ?? [];
        bucket.push(a);
        types.set(a.event_type, bucket);
      }
      return {
        kind,
        label: KIND_LABEL[kind],
        count: mine.length,
        sections: [...types.entries()]
          // Busiest type first, so the dominant story in a long record leads.
          .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
          .map(([type, list]) => ({ type, assessments: list })),
      };
    })
    .filter((group) => group.count > 0);
}

/* --- source standing --------------------------------------------------------- */

/**
 * How prominently to show a report's source standing.
 *
 * Decided by the backend, read here (D36). The tone drives colour only; the label is
 * always spelled out beside it, because a badge whose meaning is carried by colour alone
 * is a badge half the readers cannot use.
 */
export function standingTone(standing: Assessment["source_standing"]): string {
  return standing;
}

/** Whether this standing is worth calling out on a compact row rather than in detail. */
export function isWeakSource(standing: Assessment["source_standing"]): boolean {
  return standing === "UNRECOGNISED" || standing === "SYNDICATED_RELEASE";
}

/* --- sorting the board ------------------------------------------------------- */

/**
 * How the reader wants their *companies* arranged (D38).
 *
 * A presentation axis, and deliberately a different question from the one the backend
 * answers. Canonical order ranks **developments** by severity and recency (D26); this
 * arranges **companies** by what the reader is looking for right now. Choosing "biggest
 * gainers" must not change what any development is worth, or the order of anything
 * outside this list.
 */
export type SortMode = "attention" | "gainers" | "losers" | "movement" | "alphabetical" | "recent";

export const SORT_LABELS: Record<SortMode, string> = {
  attention: "What needs you",
  gainers: "Biggest gainers",
  losers: "Biggest losers",
  movement: "Largest move",
  alphabetical: "A–Z",
  recent: "Recently added",
};

/**
 * Sort loaded rows. No request is made: every value this reads is already on screen.
 *
 * A company with no stored price sorts last in every price mode rather than being treated
 * as flat — missing data is not a zero move, and putting it in the middle of the list
 * would say it was.
 */
export function sortRows(
  rows: CompanyRow[],
  changeFor: (symbol: string) => number | null | undefined,
  mode: SortMode,
): CompanyRow[] {
  if (mode === "attention") return rows;

  const change = (row: CompanyRow) => {
    const value = changeFor(row.symbol);
    return value === null || value === undefined ? null : value;
  };
  // Sorts last whichever direction we are sorting in.
  const byPrice = (pick: (value: number) => number) => (a: CompanyRow, b: CompanyRow) => {
    const left = change(a);
    const right = change(b);
    if (left === null && right === null) return a.symbol.localeCompare(b.symbol);
    if (left === null) return 1;
    if (right === null) return -1;
    return pick(right) - pick(left) || a.symbol.localeCompare(b.symbol);
  };

  const sorted = [...rows];
  switch (mode) {
    case "gainers":
      return sorted.sort(byPrice((value) => value));
    case "losers":
      return sorted.sort(byPrice((value) => -value));
    case "movement":
      return sorted.sort(byPrice(Math.abs));
    case "alphabetical":
      return sorted.sort((a, b) => a.symbol.localeCompare(b.symbol));
    case "recent":
      return sorted.sort(
        (a, b) => b.addedAt.localeCompare(a.addedAt) || a.symbol.localeCompare(b.symbol),
      );
  }
}

/* --- a company's timeline ---------------------------------------------------- */

export interface TimelineEntry {
  assessment: Assessment;
  kind: Kind;
  label: string;
}

/**
 * One company's record in the order it happened, newest first.
 *
 * Derived from the assessments already loaded for the detail view — no request, no second
 * store, no new event type. `groupByKind` answers "what kinds of thing happened"; this
 * answers "what happened around that price move", which is the question a reader has when
 * they are looking at a chart.
 */
export function byTime(assessments: Assessment[]): TimelineEntry[] {
  return byRecency(assessments).map((assessment) => ({
    assessment,
    kind: kindOf(assessment),
    label: KIND_LABEL[kindOf(assessment)],
  }));
}

/* --- one development, several records ---------------------------------------- */

export interface AttentionGroup {
  /** The development key the backend assigned. Never computed here (D43). */
  developmentId: string;
  /** Canonically first, so its verdict and reasoning lead the card. */
  primary: AttentionItem;
  /** Later records for the same development, in the order they arrived. */
  related: AttentionItem[];
  /** Independent publishers across the whole development, counted server-side by D13. */
  sources: number;
}

/**
 * Collapse attention items into developments.
 *
 * A `groupBy` and nothing more: which records belong together was decided server-side,
 * where the calibrated similarity relation lives. Reimplementing that judgement here would
 * be a second copy of a tuned rule, and the copy nobody tested would eventually disagree.
 *
 * Order is preserved exactly — groups appear in the position of their primary, so the
 * backend's canonical ordering (D26) survives grouping untouched.
 */
export function groupAttentionItems(items: AttentionItem[]): AttentionGroup[] {
  const groups: AttentionGroup[] = [];
  const byId = new Map<string, AttentionGroup>();

  for (const item of items) {
    const existing = byId.get(item.development_id);
    if (existing === undefined) {
      const group: AttentionGroup = {
        developmentId: item.development_id,
        primary: item,
        related: [],
        sources: item.development_sources,
      };
      byId.set(item.development_id, group);
      groups.push(group);
      continue;
    }
    existing.related.push(item);
  }
  return groups;
}

/**
 * Evidence across a development, deduplicated for display.
 *
 * Render-time only: no stored evidence relationship changes, and the same source cited by
 * two records is one source to a reader.
 */
export function groupedEvidence(group: AttentionGroup) {
  const seen = new Map<string, AttentionItem["assessment"]["evidence"][number]>();
  for (const item of [group.primary, ...group.related]) {
    for (const evidence of item.assessment.evidence) {
      if (!seen.has(evidence.ref)) seen.set(evidence.ref, evidence);
    }
  }
  return [...seen.values()];
}

/** Whether a development's later records reached a different verdict worth showing. */
export function differingVerdicts(group: AttentionGroup): boolean {
  return group.related.some(
    (item) => item.assessment.attention !== group.primary.assessment.attention,
  );
}

/**
 * The developments the hero previews.
 *
 * A filter over the grouped, canonically ordered items — never a re-ranking. `HIGH` and
 * `MEDIUM` are the levels that ask something of a reader; `LOW` belongs in the list below,
 * where a reader is already scanning rather than being told.
 */
export function demandingDevelopments(items: AttentionItem[]): AttentionGroup[] {
  return groupAttentionItems(items).filter(
    (group) =>
      group.primary.assessment.attention === "HIGH" ||
      group.primary.assessment.attention === "MEDIUM",
  );
}
