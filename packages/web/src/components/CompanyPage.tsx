import { useEffect, useState } from "react";

import {
  intelligence,
  prices,
  review,
  watchPoints,
  watchlist,
  type Assessment,
  type ReviewPage,
  type WatchedCompany,
  type WatchPoint,
} from "../lib/api";
import { buildRows, type CompanyRow } from "../lib/rows";
import CompanyDetail from "./CompanyDetail";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      row: CompanyRow;
      membership: WatchedCompany | undefined;
      known: Assessment[];
      points: WatchPoint[];
      lastClose: number | null;
    };

export default function CompanyPage() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const symbol = new URLSearchParams(window.location.search).get("symbol")?.toUpperCase();
    if (!symbol) {
      setState({ kind: "error", message: "Choose a company from your watchlist first." });
      return;
    }
    Promise.all([
      watchlist.list(),
      review.open(),
      intelligence.all(),
      watchPoints.list(),
      prices.status(),
    ])
      .then(([listed, page, all, levels, statuses]) => {
        const row = buildRows(listed.companies, page as ReviewPage, all.assessments).find(
          (item) => item.symbol === symbol,
        );
        if (!row) throw new Error("That company is not on this watchlist.");
        setState({
          kind: "ready",
          row,
          membership: listed.companies.find((item) => item.symbol === symbol),
          known: all.assessments,
          points: levels.points,
          lastClose: statuses.statuses.find((item) => item.symbol === symbol)?.close ?? null,
        });
      })
      .catch((error: unknown) =>
        setState({ kind: "error", message: error instanceof Error ? error.message : "Could not load company." }),
      );
  }, [reloads]);

  if (state.kind === "loading") return <main className="main"><div className="skeleton" aria-busy="true" /></main>;
  if (state.kind === "error") {
    return <main className="main"><div className="notice error">{state.message} <a href="/">Back to watchlist</a></div></main>;
  }
  return (
    <CompanyDetail
      row={state.row}
      membership={state.membership}
      known={state.known}
      points={state.points}
      lastClose={state.lastClose}
      onChanged={() => setReloads((count) => count + 1)}
      onClose={() => window.location.assign("/")}
    />
  );
}
