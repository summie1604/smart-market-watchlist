/**
 * "Watch out for this" — a level on one company, and what to say when it is reached.
 *
 * The bar sets a price level and a note. The backend infers the direction from the last
 * stored close, refuses a level already reached, and settles the point during the
 * scheduled ingestion cycle against stored end-of-day closes. This component sends a
 * number and a sentence, and renders what comes back; it never decides whether a level
 * was met (D37).
 *
 * Deliberately not a notification. The product is pull-based (VISION §17): a level being
 * reached waits on the board for the next visit rather than interrupting the reader.
 */

import { useState } from "react";
import { watchPoints, type WatchPoint } from "../lib/api";

export default function WatchPointBar({
  symbol,
  points,
  lastClose,
  onChanged,
}: {
  symbol: string;
  points: WatchPoint[];
  lastClose: number | null | undefined;
  onChanged: () => void;
}) {
  const [level, setLevel] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const mine = points.filter((point) => point.symbol === symbol);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const value = Number(level);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Enter a price level to watch for.");
      return;
    }
    setBusy(true);
    setError("");
    watchPoints
      .add(symbol, value, note)
      .then(() => {
        setLevel("");
        setNote("");
        onChanged();
      })
      // The server's refusal is the message. It knows the last stored close and this
      // component does not, so restating it here would eventually contradict it.
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not set that level."))
      .finally(() => setBusy(false));
  };

  return (
    <section className="watch" aria-label={`Watch out for a price level on ${symbol}`}>
      <div className="watch-head">
        <h3>Watch out for</h3>
        <p>
          Tell us a price to look for and why. We check it against stored end-of-day
          closes and show it here when it happens — no alerts, no predictions.
        </p>
      </div>

      <form className="watch-form" onSubmit={submit}>
        <label className="visually-hidden" htmlFor={`level-${symbol}`}>
          Price level for {symbol}
        </label>
        <input
          id={`level-${symbol}`}
          className="watch-level"
          type="number"
          inputMode="decimal"
          step="0.05"
          min="0"
          placeholder={lastClose ? `e.g. ${Math.round(lastClose * 1.1)}` : "price"}
          value={level}
          onChange={(event) => setLevel(event.target.value)}
        />
        <label className="visually-hidden" htmlFor={`note-${symbol}`}>
          What to watch out for
        </label>
        <input
          id={`note-${symbol}`}
          className="watch-note"
          type="text"
          maxLength={200}
          placeholder="Watch out for… (optional)"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        <button type="submit" className="primary" disabled={busy}>
          Set
        </button>
      </form>

      {lastClose ? (
        <p className="watch-hint">
          Last stored close ₹{lastClose.toLocaleString("en-IN", { maximumFractionDigits: 2 })}.
          A level above it waits for a rise, below it for a fall.
        </p>
      ) : (
        <p className="watch-hint">
          No stored end-of-day close for this company yet, so there is nothing to measure a
          level against.
        </p>
      )}

      {error && <p className="notice error">{error}</p>}

      {mine.length > 0 && (
        <ul className="watch-list">
          {mine.map((point) => (
            <li key={point.point_id} data-reached={point.triggered_on !== null}>
              <span className="watch-level-read">
                {point.direction === "ABOVE" ? "at or above" : "at or below"} ₹
                {point.level.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </span>
              {point.note && <span className="watch-note-read">{point.note}</span>}
              {point.triggered_on !== null ? (
                <span className="watch-reached">
                  reached — closed ₹{point.triggered_close?.toLocaleString("en-IN")} on{" "}
                  {point.triggered_on}
                </span>
              ) : (
                <span className="watch-waiting">waiting</span>
              )}
              <button
                type="button"
                className="ghost"
                onClick={() => void watchPoints.remove(point.point_id).then(onChanged)}
                aria-label={`Remove the ₹${point.level} level on ${symbol}`}
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
