/**
 * Everything we hold about one company.
 *
 * A dedicated page reached from a watchlist card. It renders verdicts and never produces one: attention and confidence are
 * copied as two separate values, the reason codes are the engine's own, corroboration
 * counts independent publishers rather than articles, and a contradiction is a link the
 * backend decided (D29).
 */

import { useEffect, useRef, useState } from "react";
import type { Assessment, WatchedCompany, WatchPoint } from "../lib/api";
import { byTime, disputedBy, whenText, type CompanyRow } from "../lib/rows";
import Assistant from "./Assistant";
import WatchPointBar from "./WatchPoints";
import PriceChart from "./PriceChart";

export default function CompanyDetail({
  row,
  membership,
  known,
  points,
  lastClose,
  onChanged,
  onClose,
}: {
  row: CompanyRow;
  membership: WatchedCompany | undefined;
  known: Assessment[];
  points: WatchPoint[];
  lastClose: number | null | undefined;
  onChanged: () => void;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Focus starts at the back control so a keyboard reader has an immediate, clear exit.
    const restore = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      restore?.focus?.();
    };
  }, [onClose]);

  const heading = `${row.symbol}-detail-heading`;

  return (
    <main className="detail page-detail" aria-labelledby={heading}>
        <div className="detail-head">
          <div className="detail-title">
            <h2 id={heading}>
              {row.symbol} <span className="row-co">{row.company}</span>
            </h2>
            <p>
              {row.history.length} {row.history.length === 1 ? "development" : "developments"} on
              record
              {row.coverageTier === "LIMITED" && " · limited coverage"}
              {/* Basic company information, from the context the engine already uses to
                  judge this security — not a new profile source. */}
              {membership?.sector_label && ` · judged against ${membership.sector_label}`}
              {membership && ` · watched since ${membership.added_at.slice(0, 10)}`}
            </p>
          </div>
          <button ref={closeButton} type="button" onClick={onClose}>
            Back to watchlist
          </button>
        </div>

        <div className="detail-body">
          {(row.state === "unable" || row.state === "new" || row.state === "quiet") && (
            <p className={`notice ${row.state === "unable" ? "warn" : ""}`}>{row.detail}</p>
          )}

          {membership !== undefined && (membership.reason || membership.watch_for) && (
            <section className="yours">
              <h3>What you said</h3>
              {membership.reason && <p>{membership.reason}</p>}
              {membership.watch_for && (
                <p>
                  <b>Watching for:</b> {membership.watch_for}
                </p>
              )}
            </section>
          )}

          <WatchPointBar
            symbol={row.symbol}
            points={points}
            lastClose={lastClose}
            onChanged={onChanged}
          />

          <PriceChart symbol={row.symbol} />

          <AlertHistory points={points.filter((point) => point.symbol === row.symbol)} />

          <Timeline history={row.history} />

          {row.history.length === 0 ? (
            <div className="blank">
              <h3>Nothing recorded yet</h3>
              <p>
                We are watching this company. As soon as something is assessed, it appears
                here.
              </p>
            </div>
          ) : (
            <section className="group">
              <div className="group-head">
                <h3>News & market events</h3>
                <span className="n">{row.history.length}</span>
              </div>
              <p className="group-note">Most important first. Open an item for the evidence and why it matters.</p>
              {byImportance(row.history).map((assessment) => (
                <EventCard key={assessment.event_id} assessment={assessment} known={known} />
              ))}
            </section>
          )}
        </div>

      {/* The same assistant as the board, carrying this company as context so "why did
          this fall?" needs no ticker (D40). */}
      <Assistant symbol={row.symbol} />
    </main>
  );
}

/**
 * Every level this reader set on this company, and where each one stands (D37).
 *
 * The same records `/v1/watch-points` already returned — the history *is* the alert, not a
 * copy of it, so a triggered point keeps its note, its baseline and the session that
 * satisfied it in one row. Severity is deliberately absent: a level the reader chose has
 * no severity we could honestly assign, and the engine's own alerts carry theirs as an
 * attention level on the development itself.
 */
function AlertHistory({ points }: { points: WatchPoint[] }) {
  if (points.length === 0) return null;

  return (
    <section className="alerts" aria-label="Alert history for this company">
      <div className="group-head">
        <h3>Your alerts</h3>
        <span className="n">{points.length}</span>
      </div>
      <ul className="alert-rows">
        {points.map((point) => (
          <li key={point.point_id} data-state={point.triggered_on ? "reached" : "waiting"}>
            <span className="alert-cond">
              {describeCondition(point)}
            </span>
            {point.note && <span className="alert-note">{point.note}</span>}
            <span className="alert-when">
              {point.triggered_on
                ? `reached — closed ₹${point.triggered_close?.toLocaleString("en-IN")} on ${point.triggered_on}`
                : `set ${point.created_at.slice(0, 10)}`}
            </span>
            <span className="alert-state">
              {point.triggered_on === null
                ? "waiting"
                : point.acknowledged_at === null
                  ? "unseen"
                  : "seen"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The condition in the reader's words. The baseline is shown because it is the thing a
 *  percentage point is measured against, and it never moves (D39). */
function describeCondition(point: WatchPoint): string {
  const level = point.level.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  switch (point.direction) {
    case "ABOVE":
      return `at or above ₹${level}`;
    case "BELOW":
      return `at or below ₹${level}`;
    case "PERCENT_UP":
      return `up ${level}% from ₹${point.created_close?.toLocaleString("en-IN") ?? "—"}`;
    case "PERCENT_DOWN":
      return `down ${level}% from ₹${point.created_close?.toLocaleString("en-IN") ?? "—"}`;
  }
}

/**
 * What happened, in the order it happened.
 *
 * Built from the assessments already loaded for this page — no request, no new event
 * table. `groupByKind` below answers "what kinds of thing happened"; this answers "what
 * happened around that move", which is the question a chart provokes.
 */
function Timeline({ history }: { history: Assessment[] }) {
  const entries = byTime(history).slice(0, 12);
  if (entries.length === 0) return null;

  return (
    <section className="timeline" aria-label="What happened, in order">
      <div className="group-head">
        <h3>Timeline</h3>
        <span className="n">{entries.length}</span>
      </div>
      <ol className="timeline-rows">
        {entries.map(({ assessment, kind, label }) => (
          <li key={assessment.event_id} data-kind={kind}>
            <span className="tl-when">{whenText(assessment.occurred_at)}</span>
            <span className="tl-kind">{label}</span>
            <span className="tl-what">{assessment.description}</span>
            <span className="badge" data-tone={assessment.attention}>
              {assessment.attention.replace(/_/g, " ").toLowerCase()}
            </span>
          </li>
        ))}
      </ol>
      <p className="tl-note">
        Ordered by when each development happened. Sitting next to each other in time is
        not evidence that one caused the other.
      </p>
    </section>
  );
}

export function EventCard({
  assessment: a,
  known,
}: {
  assessment: Assessment;
  known: Assessment[];
}) {
  const [expanded, setExpanded] = useState(false);
  // Corroboration gets its own line below, so its reasons are not repeated as bullets.
  // Filtering by code selects what to show; it never changes what any of it means.
  const corroborationCodes = new Set(["INDEPENDENT_CORROBORATION", "SINGLE_SOURCE_ONLY"]);
  const why = a.reasons.filter((r) => !corroborationCodes.has(r.code));
  const supports = why.filter((r) => r.direction === "+");
  const against = why.filter((r) => r.direction === "-");
  const missing = a.coverage.records.filter((c) => c.status !== "OK");
  const other = disputedBy(a, known);

  return (
    <article className="event" data-tone={a.attention} data-state={a.contradiction.state}>
      <button type="button" className="event-toggle" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        <span className="event-head">
          <span className="badge" data-tone={a.attention}>
            {a.attention.replace(/_/g, " ").toLowerCase()}
          </span>
          <span className="badge soft">{a.confidence.toLowerCase()} confidence</span>
        <span className="badge standing" data-standing={a.source_standing}>
          {a.source_standing_label}
        </span>
          <span className="event-kind">{a.event_type}</span>
          <span className="event-kind">· {whenText(a.occurred_at)}</span>
        </span>
        <span className="event-summary">{a.description}</span>
        <span className="event-expand">{expanded ? "Hide details" : "Why this matters + source"}</span>
      </button>

      {expanded && <>

      {a.focus.length > 0 && (
        <p className="matched">
          Matches your focus — {a.focus.map((m) => m.why).join("; ")}.
        </p>
      )}

      {/* Both records stay readable and linked; neither is deleted or rewritten. */}
      {a.contradiction.disputed_by !== null && (
        <p className={`dispute ${a.contradiction.confirmed ? "confirmed" : "possible"}`}>
          <b>
            {a.contradiction.state === "WITHDRAWN"
              ? "Withdrawn"
              : a.contradiction.confirmed
                ? "Disputed"
                : "Possibly related"}
          </b>{" "}
          {a.contradiction.detail}
          {other !== null && <span className="dispute-of"> Later report: “{other.description}”</span>}
          {a.contradiction.confirmed && (
            <span className="dispute-of">
              {" "}
              This lowers how sure we are, not how much it matters.
            </span>
          )}
        </p>
      )}

      {why.length > 0 && <p className="why-title">Why this matters</p>}
      <ul>
        {supports.map((r) => (
          <li key={r.code}>{r.detail}</li>
        ))}
        {against.map((r) => (
          <li key={r.code} className="against">
            {r.detail}
          </li>
        ))}
      </ul>

      <p className="event-facts">
        {a.corroboration.summary}
        {a.corroboration.has_authoritative && " · includes an exchange filing"}
        {a.corroboration.article_count > a.corroboration.independent_source_count &&
          " · some reports share a newsroom"}
      </p>

      {missing.length > 0 && (
        <p className="event-facts gap">
          Not checked when this was assessed: {missing.map((m) => sourceLabel(m.source)).join(", ")}
        </p>
      )}

      <ul className="sources">
        {a.evidence.map((e) => (
          <li key={e.ref}>
            {e.publisher} <span className="src-standing">{e.standing_label}</span> ·{" "}
            {whenText(e.published_at)}
            {e.url ? (
              <>
                {" · "}
                <a href={e.url} target="_blank" rel="noreferrer">
                  read the source
                </a>
              </>
            ) : (
              " · from market data"
            )}
          </li>
        ))}
      </ul>
      </>}
    </article>
  );
}

function byImportance(assessments: Assessment[]): Assessment[] {
  const order: Record<Assessment["attention"], number> = {
    HIGH: 0,
    MEDIUM: 1,
    LOW: 2,
    UNABLE_TO_EVALUATE_RELIABLY: 3,
    NO_MEANINGFUL_CHANGE: 4,
  };
  return [...assessments].sort(
    (left, right) => order[left.attention] - order[right.attention] || right.occurred_at.localeCompare(left.occurred_at),
  );
}

/** Source keys are internal; readers get the plain name. */
export function sourceLabel(source: string): string {
  const names: Record<string, string> = {
    news: "news",
    market: "market data",
    "nse-disclosures": "exchange disclosures",
  };
  return names[source] ?? source;
}
