/**
 * Data states a component must be able to communicate (DESIGN.md, presentation rules).
 *
 * Presentation only — nothing here decides a state, it only labels one. The distinction
 * that must never collapse: `no-meaningful-change` is a conclusion, `unable-to-evaluate`
 * is an admission. They never share a treatment.
 */
export const DATA_STATES = [
  "fresh",
  "stale",
  "delayed",
  "partial",
  "unavailable",
  "conflicting",
  "developing",
  "unverified",
  "no-meaningful-change",
  "unable-to-evaluate",
] as const;

export type DataState = (typeof DATA_STATES)[number];

/** How confidently the interface may speak in each state. */
export type StateTone = "settled" | "qualified" | "unknown";

const TONES: Record<DataState, StateTone> = {
  fresh: "settled",
  "no-meaningful-change": "settled",
  developing: "qualified",
  delayed: "qualified",
  stale: "qualified",
  partial: "qualified",
  unverified: "qualified",
  conflicting: "qualified",
  unavailable: "unknown",
  "unable-to-evaluate": "unknown",
};

const LABELS: Record<DataState, string> = {
  fresh: "Up to date",
  stale: "Stale",
  delayed: "Delayed",
  partial: "Partial coverage",
  unavailable: "Source unavailable",
  conflicting: "Conflicting reports",
  developing: "Developing",
  unverified: "Unverified",
  "no-meaningful-change": "No meaningful change",
  "unable-to-evaluate": "Unable to evaluate",
};

export function toneOf(state: DataState): StateTone {
  return TONES[state];
}

export function labelOf(state: DataState): string {
  return LABELS[state];
}
