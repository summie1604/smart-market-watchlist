/**
 * Step 0's surface. Deliberately ugly, and deliberately complete.
 *
 * Its job is not to look good — it is to prove the architecture can *communicate* what
 * the engine decided: the verdict, the reason codes that produced it including the ones
 * that argued against, the confidence, what could not be consulted, and a link to the
 * filing itself. If any of that turned out awkward to render, the model would be wrong
 * and we would want to know now rather than in step 6 (DESIGN.md, Step 0).
 *
 * A React island because the data is fetched per view; the page around it is static.
 */

import { useEffect, useState } from "react";
import {
  attentionLabel,
  fetchAssessments,
  type Assessment,
  type AssessmentsResponse,
  type SourceHealth,
} from "../lib/api";

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: AssessmentsResponse };

export default function AssessmentList() {
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    fetchAssessments()
      .then((data) => setLoad({ state: "ready", data }))
      .catch((error: unknown) =>
        setLoad({
          state: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        }),
      );
  }, []);

  if (load.state === "loading") return <p>Loading…</p>;

  if (load.state === "error") {
    return (
      <div>
        <p>
          <strong>Could not reach the API.</strong> {load.message}
        </p>
        <p>
          This is a failure to load, not a finding about the market. Start the backend
          with <code>make run-api</code>, then <code>POST /ingest</code>.
        </p>
      </div>
    );
  }

  const { assessments, source_health } = load.data;

  // Rendered in the order the backend returned. Canonical ranking is the engine's
  // answer to a product question; re-deriving it here would be a second, divergent one.
  return (
    <div>
      <SourceHealthBanner health={source_health} />
      {assessments.length === 0 ? (
        <p>
          No assessments stored. Run <code>curl -X POST localhost:8000/ingest</code>.
          An empty store means we have not looked — which is not a finding about the
          market.
        </p>
      ) : (
        <>
          <p>
            <strong>{assessments.length} assessed disclosures</strong>, in the order the
            engine ranked them.
          </p>
          {assessments.map((a) => (
            <AssessmentCard key={a.event_id} assessment={a} />
          ))}
        </>
      )}
    </div>
  );
}

/**
 * Current source health, shown above the verdicts.
 *
 * Deliberately prominent when unhealthy: the verdicts below may be from an earlier,
 * successful run, and a reader must not take their presence as evidence that the
 * sources behind them are working now.
 */
function SourceHealthBanner({ health }: { health: SourceHealth | null }) {
  if (health === null) {
    return (
      <p style={{ border: "1px solid #999", padding: "0.5rem" }}>
        <strong>No ingest has run.</strong> Nothing here has been looked at yet.
      </p>
    );
  }

  const failed = health.records.filter((r) => r.status !== "OK");
  return (
    <div
      style={{
        border: "1px solid #999",
        borderLeftWidth: "6px",
        borderLeftColor: health.healthy ? "#2a7" : "#c33",
        padding: "0.5rem",
        marginBottom: "1rem",
      }}
    >
      <strong>
        {health.healthy
          ? `Sources healthy as of ${health.started_at}.`
          : `Last ingest could not read ${health.source}.`}
      </strong>
      {!health.healthy && (
        <p style={{ margin: "0.25rem 0" }}>
          Verdicts below may predate this failure. Their presence is not evidence that
          the sources are working now.
        </p>
      )}
      {failed.length > 0 && (
        <ul style={{ margin: "0.25rem 0" }}>
          {failed.map((r) => (
            <li key={r.source}>
              <code>
                {r.source}: {r.status}
              </code>
              {r.detail && ` — ${r.detail}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AssessmentCard({ assessment: a }: { assessment: Assessment }) {
  const unable = a.attention === "UNABLE_TO_EVALUATE_RELIABLY";
  return (
    <article
      style={{
        border: "1px solid #999",
        borderLeftWidth: "6px",
        borderLeftColor: unable ? "#b58900" : "#333",
        padding: "0.75rem",
        margin: "0.75rem 0",
      }}
    >
      <h3 style={{ margin: "0 0 0.25rem" }}>
        {a.symbol} — {attentionLabel(a.attention)}
      </h3>
      <p style={{ margin: "0 0 0.5rem", fontSize: "0.9em" }}>
        {a.company} · {a.event_type} · confidence {a.confidence} · score {a.score} ·
        rules {a.scoring_version}
      </p>
      <p style={{ margin: "0 0 0.5rem" }}>{a.description}</p>

      <details open>
        <summary>Why you are seeing this</summary>
        <ul style={{ margin: "0.5rem 0" }}>
          {a.reasons.map((r) => (
            <li key={r.code}>
              <code>
                {r.direction} {r.code} ({r.contribution > 0 ? "+" : ""}
                {r.contribution})
              </code>{" "}
              — {r.detail}
            </li>
          ))}
        </ul>
      </details>

      <details>
        <summary>
          Coverage: {a.coverage.complete ? "complete" : "incomplete"}
        </summary>
        {a.coverage.note && <p>{a.coverage.note}</p>}
        <ul>
          {a.coverage.records.map((c) => (
            <li key={c.source}>
              <code>
                {c.source}: {c.status}
              </code>
              {c.detail && ` — ${c.detail}`}
            </li>
          ))}
        </ul>
      </details>

      <details>
        <summary>Evidence</summary>
        <ul>
          {a.evidence.map((e) => (
            <li key={e.ref}>
              <code>{e.tier}</code> · {e.publisher} · {e.published_at} ·{" "}
              {e.url ? (
                <a href={e.url} target="_blank" rel="noreferrer">
                  source document
                </a>
              ) : (
                // Computed evidence has no document to link to. A dead link labelled
                // "filing" would claim a source that does not exist.
                <span>derived from primary market data ({e.ref})</span>
              )}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
