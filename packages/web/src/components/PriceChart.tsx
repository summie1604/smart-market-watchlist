/**
 * Price context: the company against its benchmarks.
 *
 * Draws points the backend already aligned and rebased (D28). Nothing here computes a
 * return, aligns a session or decides which benchmark is usable — that is a financial
 * calculation and it lives in `core/prices.py`. This file turns numbers into a path and
 * says plainly what the picture does not cover.
 *
 * It lives inside a company's detail and never on the board, because a price chart on the
 * main surface would make price the subject.
 */

import { useEffect, useState } from "react";
import { prices, type PriceComparison, type PriceRange, type PriceSeries } from "../lib/api";

/* Every range is end-of-day (D28). "1D" is the latest stored session against the one
 * before it, not a day of intraday ticks — so the labels say sessions, and the basis line
 * under the chart repeats it. Naming it "1D" without that would imply a feed we do not
 * have and deliberately did not add. */
const RANGES: { value: PriceRange; label: string }[] = [
  { value: "1d", label: "1D" },
  { value: "1w", label: "1W" },
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
];

const ROLE_CLASS: Record<PriceSeries["role"], string> = {
  security: "series-security",
  sector: "series-sector",
  broad: "series-broad",
};

export default function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState<PriceRange>("6m");
  const [data, setData] = useState<PriceComparison | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setState("loading");
    prices
      .get(symbol, range)
      .then((result) => {
        if (!live) return;
        setData(result);
        setState("ready");
      })
      .catch((e: unknown) => {
        if (!live) return;
        setError(e instanceof Error ? e.message : "Price history could not be loaded.");
        setState("error");
      });
    return () => {
      live = false;
    };
  }, [symbol, range]);

  return (
    <section className="chart" aria-label={`Price context for ${symbol}`}>
      <div className="chart-head">
        <h3>Price context</h3>
        <div className="ranges" role="group" aria-label="Chart range, in trading sessions">
          {RANGES.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={range === option.value}
              onClick={() => setRange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {state === "loading" && <div className="chart-skeleton" aria-busy="true" />}

      {state === "error" && (
        <p className="chart-note">
          {error} No chart is drawn rather than an approximate one.
        </p>
      )}

      {state === "ready" && data !== null && (
        <>
          {data.series.length === 0 ? (
            <p className="chart-note">
              {data.notes[0] ?? "No end-of-day data is available for this range."}
            </p>
          ) : (
            <>
              <Plot data={data} />
              <ul className="legend">
                {data.series.map((series) => (
                  <li key={series.symbol} className={ROLE_CLASS[series.role]}>
                    <span className="swatch" aria-hidden="true" />
                    {series.label}
                    <b>
                      {series.change_pct >= 0 ? "+" : ""}
                      {series.change_pct.toFixed(2)}%
                    </b>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="chart-basis">
            {data.basis} Every range is measured in completed trading sessions, not
            intraday ticks — “1D” is the latest stored session against the one before it.
            {" "}
            {data.covered_from !== null && (
              <>
                {" "}
                {data.sessions} sessions, {data.covered_from} to {data.covered_to}.
              </>
            )}
          </p>
          {data.notes.map((note) => (
            <p className="chart-note" key={note}>
              {note}
            </p>
          ))}
        </>
      )}
    </section>
  );
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD = 8;

/**
 * The plot itself.
 *
 * The only arithmetic here is turning a rebased value into a y coordinate — geometry, not
 * finance. The scale spans every series so the lines are comparable, which is the whole
 * point of the comparison.
 */
function Plot({ data }: { data: PriceComparison }) {
  const values = data.series.flatMap((s) => s.points.map((p) => p.value));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const count = Math.max(...data.series.map((s) => s.points.length));

  const path = (series: PriceSeries) =>
    series.points
      .map((point, index) => {
        const x = PAD + (index / Math.max(count - 1, 1)) * (WIDTH - PAD * 2);
        const y = HEIGHT - PAD - ((point.value - low) / span) * (HEIGHT - PAD * 2);
        return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");

  const summary = data.series
    .map((s) => `${s.label} ${s.change_pct >= 0 ? "up" : "down"} ${Math.abs(s.change_pct).toFixed(1)} percent`)
    .join("; ");

  return (
    <div className="chart-plot">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Rebased to 100 over ${data.sessions} shared sessions. ${summary}.`}
      >
        {/* The rebasing baseline: everything starts here, so crossing it is the story. */}
        <line
          className="baseline"
          x1={PAD}
          x2={WIDTH - PAD}
          y1={HEIGHT - PAD - ((100 - low) / span) * (HEIGHT - PAD * 2)}
          y2={HEIGHT - PAD - ((100 - low) / span) * (HEIGHT - PAD * 2)}
        />
        {data.series.map((series) => (
          <path key={series.symbol} className={ROLE_CLASS[series.role]} d={path(series)} />
        ))}
      </svg>
    </div>
  );
}
