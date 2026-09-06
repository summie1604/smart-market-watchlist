/**
 * Adding a company, and asking why.
 *
 * Three questions on the way in — why you follow it, what you want to watch for, and
 * which focus areas apply — all optional and skippable in one action. The questions are
 * worth asking because a watchlist entry with a stated purpose is worth more than one
 * without; they are never worth blocking on, so the primary button adds the company
 * whether or not anything was answered (D27).
 *
 * Only the tags do anything, and all they do is filter and annotate. The free text is
 * kept for the reader's own reference and is never parsed into behaviour.
 */

import { useEffect, useRef, useState } from "react";
import type { FocusTagInfo, Interests, UniverseCompany, WatchedCompany } from "../lib/api";

export default function AddCompany({
  supported,
  watched,
  focusTags,
  busy,
  onAdd,
}: {
  supported: UniverseCompany[];
  watched: WatchedCompany[];
  focusTags: FocusTagInfo[];
  busy: boolean;
  onAdd: (symbol: string, interests: Interests) => void;
}) {
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<UniverseCompany | null>(null);
  const [reason, setReason] = useState("");
  const [watchFor, setWatchFor] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const firstField = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (chosen !== null) firstField.current?.focus();
  }, [chosen]);

  const already = new Set(watched.map((w) => w.symbol));
  const needle = query.trim().toLowerCase();
  const matches = needle
    ? supported
        .filter((c) => !already.has(c.symbol))
        .filter((c) => `${c.symbol} ${c.company}`.toLowerCase().includes(needle))
        .slice(0, 6)
    : [];

  const reset = () => {
    setChosen(null);
    setQuery("");
    setReason("");
    setWatchFor("");
    setTags([]);
  };

  const submit = () => {
    if (chosen === null) return;
    onAdd(chosen.symbol, { reason, watch_for: watchFor, tags });
    reset();
  };

  if (chosen !== null) {
    return (
      <form
        className="interests"
        aria-label={`What are you watching ${chosen.symbol} for?`}
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="interests-head">
          <h2>
            {chosen.symbol} <span>{chosen.company}</span>
          </h2>
          <p>
            Every answer is optional. Only the focus areas change what you see, and they
            only ever narrow — a high-attention development is never hidden.
          </p>
        </div>

        <label>
          Why are you following this company?
          <textarea
            ref={firstField}
            value={reason}
            rows={2}
            maxLength={500}
            placeholder="Largest holding; I care about the refining margin."
            onChange={(e) => setReason(e.target.value)}
          />
        </label>

        <label>
          What do you want to watch for?
          <textarea
            value={watchFor}
            rows={2}
            maxLength={500}
            placeholder="Anything about capacity expansion or a regulatory ruling."
            onChange={(e) => setWatchFor(e.target.value)}
          />
        </label>

        <fieldset className="tagset">
          <legend>Focus areas</legend>
          {focusTags.map((tag) => {
            const on = tags.includes(tag.tag);
            return (
              <button
                key={tag.tag}
                type="button"
                className="chip"
                aria-pressed={on}
                title={`Matches developments that ${tag.because}`}
                onClick={() =>
                  setTags(on ? tags.filter((t) => t !== tag.tag) : [...tags, tag.tag])
                }
              >
                {tag.label}
              </button>
            );
          })}
        </fieldset>

        <div className="interests-foot">
          <button type="submit" className="primary" disabled={busy}>
            Add {chosen.symbol}
          </button>
          <button type="button" onClick={reset}>
            Cancel
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="toolbar">
      <div className="search">
        <label className="visually-hidden" htmlFor="add-company">
          Search companies to add
        </label>
        <input
          id="add-company"
          type="search"
          autoComplete="off"
          placeholder="Add a company — try Reliance, Infosys, HDFC"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {needle !== "" && (
          <div className="suggestions">
            {matches.length === 0 ? (
              <p className="no-match">
                Nothing in the supported universe matches “{query.trim()}”. We cover a
                curated set of NSE securities rather than serving the rest badly.
              </p>
            ) : (
              matches.map((c) => (
                <button key={c.symbol} type="button" onClick={() => setChosen(c)}>
                  <span className="sym">{c.symbol}</span>
                  <span className="co">{c.company}</span>
                  <span className="tier">{c.coverage_tier.toLowerCase()} coverage</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
