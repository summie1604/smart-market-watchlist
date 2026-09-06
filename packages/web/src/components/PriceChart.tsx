/**
 * Price context: the company against its benchmarks, with what happened marked on it.
 *
 * Draws points the backend already aligned and rebased (D28). Nothing here computes a
 * return, aligns a session or decides which benchmark is usable — that is a financial
 * calculation and it lives in `core/prices.py`. This file turns numbers into a path and
 * says plainly what the picture does not cover.
 *
 * Developments are marked on the line at the session they occurred in. That is a
 * *coincidence in time* and the interface says so: this product does not assert that a
 * headline moved a price, and a marker is not a claim of impact (VISION §13). The engine
 * has one reason code for the overlap — `NEWS_COINCIDES_WITH_MOVE` — and it is worded the
 * same careful way.
 *
 * It lives inside a company's detail and never on the board, because a price chart on the
 * main surface would make price the subject.
 */

import { useEffect, useMemo, useState } from "react";
import {
  prices,
  type Assessment,
  type PriceComparison,
  type PriceRange,
  type PriceSeries,
} from "../lib/api";
import { attentionLabel, whenText } from "../lib/rows";

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

export default function PriceChart({
  symbol,
  developments = [],
}: {
  symbol: string;
  /** Developments already loaded for this company. Marked, never interpreted. */
  developments?: Assessment[];
}) {
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
        setError(
          e instanceof Error ? e.message : "Price history could not be loaded.",
        );
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
      </div>

      {state === "loading" && (
        <div className="chart-skeleton" aria-busy="true" />
      )}

      {state === "error" && (
        <p className="chart-note">
          {error} No chart is drawn rather than an approximate one.
        </p>
      )}

      {state === "ready" && data !== null && (
        <>
          {data.series.length === 0 ? (
            <p className="chart-note">
              {data.notes[0] ??
                "No end-of-day data is available for this range."}
            </p>
          ) : (
            <>
              <Plot data={data} developments={developments} />
              <ul className="legend">
                {data.series.map((series) => (
                  <li key={series.symbol} className={ROLE_CLASS[series.role]}>
                    <span className="swatch" aria-hidden="true" />
                    {series.label}
                    <b className={series.change_pct >= 0 ? "up" : "down"}>
                      {series.change_pct >= 0 ? "+" : "−"}
                      {Math.abs(series.change_pct).toFixed(2)}%
                    </b>
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* The range selector sits under the chart it controls, which is where a reader
              looks once they have seen the shape and want a different span of it. */}
          <div
            className="ranges"
            role="group"
            aria-label="Chart range, in trading sessions"
          >
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

          <p className="chart-basis">
            {data.basis} Every range is measured in completed trading sessions,
            not intraday ticks — “1D” is the latest stored session against the
            one before it.{" "}
            {data.covered_from !== null && (
              <>
                {" "}
                {data.sessions} sessions, {data.covered_from} to{" "}
                {data.covered_to}.
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

const WIDTH = 760;
const HEIGHT = 300;
const LEFT = 10;
const RIGHT = 62;
/** Breathing room between the last plotted session and the value axis. */
const GUTTER = 14;
const TOP = 16;
const BOTTOM = 34;

type Marker = {
  key: string;
  index: number;
  x: number;
  y: number;
  attention: Assessment["attention"];
  events: Assessment[];
};

/**
 * The plot itself.
 *
 * The only arithmetic here is turning a rebased value into a y coordinate — geometry, not
 * finance. The scale spans every series so the lines are comparable, which is the whole
 * point of the comparison.
 */
function Plot({
  data,
  developments,
}: {
  data: PriceComparison;
  developments: Assessment[];
}) {
  const [active, setActive] = useState<string | null>(null);

  const values = data.series.flatMap((s) => s.points.map((p) => p.value));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const count = Math.max(...data.series.map((s) => s.points.length));

  const xOf = (index: number) =>
    LEFT + (index / Math.max(count - 1, 1)) * (WIDTH - LEFT - RIGHT - GUTTER);
  const yOf = (value: number) =>
    HEIGHT - BOTTOM - ((value - low) / span) * (HEIGHT - TOP - BOTTOM);

  const path = (series: PriceSeries) =>
    series.points
      .map(
        (point, index) =>
          `${index === 0 ? "M" : "L"}${xOf(index).toFixed(2)},${yOf(point.value).toFixed(2)}`,
      )
      .join(" ");

  const security = data.series.find((s) => s.role === "security");

  /* The area under the security line only. Filling every series would stack three washes
     of colour over each other and make the comparison unreadable. */
  const area =
    security === undefined || security.points.length === 0
      ? null
      : `${path(security)} L${xOf(security.points.length - 1).toFixed(2)},${HEIGHT - BOTTOM} L${xOf(0).toFixed(2)},${HEIGHT - BOTTOM} Z`;

  /* Four gridlines and their values, in the rebased units the chart is actually drawn in.
     The basis line under the chart already says what "100" means. */
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => low + f * span);

  /* Dates along the bottom, thinned to whatever fits rather than every session. */
  const dateTicks = useMemo(() => {
    if (security === undefined || security.points.length === 0) return [];
    const step = Math.max(1, Math.floor((security.points.length - 1) / 4));
    const out: { x: number; label: string }[] = [];
    for (let i = 0; i < security.points.length; i += step) {
      const point = security.points[i];
      if (point !== undefined)
        out.push({ x: xOf(i), label: shortDate(point.on) });
    }
    return out;
  }, [data, security]);

  /* One marker per session that carried a development, so two headlines on the same day
     share a bubble instead of overlapping. The session is found by the last close at or
     before the development — a development after the close belongs to that close, and one
     outside the range is dropped rather than pinned to an edge it did not happen on. */
  const markers = useMemo<Marker[]>(() => {
    if (security === undefined || security.points.length === 0) return [];
    const bySession = new Map<number, Assessment[]>();
    for (const event of developments) {
      const on = event.occurred_at.slice(0, 10);
      let index = -1;
      for (let i = 0; i < security.points.length; i += 1) {
        const point = security.points[i];
        if (point !== undefined && point.on <= on) index = i;
        else break;
      }
      if (index < 0) continue;
      bySession.set(index, [...(bySession.get(index) ?? []), event]);
    }
    return [...bySession.entries()]
      .map(([index, group]) => {
        const point = security.points[index];
        const loudest = [...group].sort(
          (a, b) => RANK[a.attention] - RANK[b.attention],
        )[0];
        return point === undefined || loudest === undefined
          ? null
          : {
              key: `${index}`,
              index,
              x: xOf(index),
              y: yOf(point.value),
              attention: loudest.attention,
              events: group,
            };
      })
      .filter((m): m is Marker => m !== null);
  }, [data, developments, security]);

  const shown = markers.find((m) => m.key === active) ?? null;

  const summary = data.series
    .map(
      (s) =>
        `${s.label} ${s.change_pct >= 0 ? "up" : "down"} ${Math.abs(s.change_pct).toFixed(1)} percent`,
    )
    .join("; ");

  const lastValue = security?.points[security.points.length - 1]?.value;

  return (
    <>
      <div className="chart-plot">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Rebased to 100 over ${data.sessions} shared sessions. ${summary}. ${markers.length} ${markers.length === 1 ? "session carries" : "sessions carry"} a recorded development.`}
        >
          <defs>
            <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity="0.3" />
              <stop offset="55%" stopColor="#22c55e" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
            </linearGradient>
          </defs>

          {ticks.map((value) => (
            <g key={value}>
              <line
                className="gridline"
                x1={LEFT}
                x2={WIDTH - RIGHT}
                y1={yOf(value)}
                y2={yOf(value)}
              />
              <text
                className="axis-value"
                x={WIDTH - RIGHT + 8}
                y={yOf(value) + 4}
              >
                {value.toFixed(1)}
              </text>
            </g>
          ))}

          {/* The rebasing baseline: everything starts here, so crossing it is the story. */}
          <line
            className="baseline"
            x1={LEFT}
            x2={WIDTH - RIGHT}
            y1={yOf(100)}
            y2={yOf(100)}
          />

          {area !== null && (
            <path className="area" d={area} fill="url(#area-fill)" />
          )}

          {data.series.map((series) => (
            <path
              key={series.symbol}
              className={ROLE_CLASS[series.role]}
              d={path(series)}
            />
          ))}

          {dateTicks.map((tick) => (
            <text
              key={tick.label}
              className="axis-date"
              x={tick.x}
              y={HEIGHT - 12}
            >
              {tick.label}
            </text>
          ))}

          {/* Where this security finished, called out the way a reader looks for it. */}
          {lastValue !== undefined && (
            <g className="last-value">
              <rect
                x={WIDTH - RIGHT + 2}
                y={yOf(lastValue) - 11}
                width={RIGHT - 6}
                height={22}
                rx={5}
              />
              <text x={WIDTH - RIGHT + 8} y={yOf(lastValue) + 4}>
                {lastValue.toFixed(1)}
              </text>
            </g>
          )}

          {/* A development sits on the line at the session it happened in. It marks
            coincidence, never cause — the caption below says so in words. */}
          {markers.map((marker) => (
            <g key={marker.key} className="marker" data-tone={marker.attention}>
              <line
                className="marker-stem"
                x1={marker.x}
                x2={marker.x}
                y1={marker.y}
                y2={HEIGHT - BOTTOM}
              />
              <circle
                className="marker-hit"
                cx={marker.x}
                cy={marker.y}
                r={14}
                tabIndex={0}
                role="button"
                aria-label={`${marker.events.length} ${marker.events.length === 1 ? "development" : "developments"} recorded around this session. ${marker.events[0]?.description ?? ""}`}
                aria-pressed={active === marker.key}
                onMouseEnter={() => setActive(marker.key)}
                onFocus={() => setActive(marker.key)}
                onClick={() =>
                  setActive(active === marker.key ? null : marker.key)
                }
              />
              <circle
                className="marker-dot"
                cx={marker.x}
                cy={marker.y}
                r={active === marker.key ? 7 : 5}
              />
              {marker.events.length > 1 && (
                <text className="marker-count" x={marker.x} y={marker.y + 3}>
                  {marker.events.length}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>

      {/* The read-out is a caption rather than a floating tooltip: it cannot fall off a
          phone screen, it survives keyboard focus, and it has room for a headline. */}
      <div className="chart-readout" aria-live="polite">
        {shown === null ? (
          <p className="chart-readout-idle">
            {markers.length === 0
              ? "No recorded development falls inside this range."
              : `${markers.length} ${markers.length === 1 ? "session" : "sessions"} on this line carried a development. Hover or focus a marker to read it.`}
          </p>
        ) : (
          <>
            <ul>
              {shown.events.map((event) => (
                <li key={event.event_id} data-tone={event.attention}>
                  <span className="badge" data-tone={event.attention}>
                    {attentionLabel(event.attention)}
                  </span>
                  <span className="chart-readout-what">
                    {event.description}
                  </span>
                  <span className="chart-readout-when">
                    {whenText(event.occurred_at)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="chart-readout-caveat">
              Marked at the session it was recorded in. Happening at the same
              time is not evidence that one caused the other.
            </p>
          </>
        )}
      </div>
    </>
  );
}

const RANK: Record<Assessment["attention"], number> = {
  HIGH: 0,
  MEDIUM: 1,
  LOW: 2,
  UNABLE_TO_EVALUATE_RELIABLY: 3,
  NO_MEANINGFUL_CHANGE: 4,
};

/** `2026-09-05` reads as `5 Sep`. Axis labels have no room for a year they all share. */
function shortDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? iso
    : parsed.toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        timeZone: "UTC",
      });
}
