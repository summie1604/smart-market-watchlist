/**
 * The Step 4 surface: sign in, curate a watchlist, read a review, complete it.
 *
 * Deliberately ugly, and deliberately thin. This component renders domain results and
 * reproduces none of the logic behind them — no ranking, no coverage judgement, no
 * checkpoint arithmetic. In particular it never computes or sends a cutoff: it returns
 * the review's id and lets the server resolve what that review committed to, which is
 * what makes a forged cutoff impossible rather than merely discouraged.
 */

import { useCallback, useEffect, useState } from "react";
import {
  attentionLabel,
  auth,
  review as reviewApi,
  watchlist as watchlistApi,
  type Account,
  type ReviewLine,
  type ReviewPage,
  type WatchedCompany,
} from "../lib/api";

export default function UserReview() {
  const [account, setAccount] = useState<Account | null>(null);
  const [companies, setCompanies] = useState<WatchedCompany[]>([]);
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [note, setNote] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [list, next] = await Promise.all([watchlistApi.list(), reviewApi.open()]);
    setCompanies(list.companies);
    setPage(next);
  }, []);

  useEffect(() => {
    auth
      .me()
      .then((me) => {
        setAccount(me);
        return refresh();
      })
      .catch(() => setAccount(null));
  }, [refresh]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await action();
      await refresh();
      setNote(success);
    } catch (error: unknown) {
      setNote(error instanceof Error ? error.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  if (account === null) {
    return <SignIn onSignedIn={(me) => { setAccount(me); void refresh(); }} />;
  }

  return (
    <div>
      <p style={{ borderBottom: "1px solid #999", paddingBottom: "0.5rem" }}>
        Signed in as <strong>{account.email}</strong>{" "}
        <button
          onClick={() =>
            void auth.logout().then(() => {
              setAccount(null);
              setPage(null);
            })
          }
        >
          Sign out
        </button>
      </p>

      {note && <p><em>{note}</em></p>}

      <Watchlist
        companies={companies}
        busy={busy}
        onAdd={(symbol) => void run(() => watchlistApi.add(symbol), `Added ${symbol}.`)}
        onRemove={(symbol) => void run(() => watchlistApi.remove(symbol), `Removed ${symbol}.`)}
      />

      {page && (
        <ReviewView
          page={page}
          busy={busy}
          onComplete={() =>
            void run(
              () => reviewApi.complete(page.review_id),
              "Review complete. The checkpoint advanced to the cutoff this review was issued with — not to the moment you clicked.",
            )
          }
        />
      )}
    </div>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (account: Account) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const submit = async (mode: "login" | "register") => {
    setError("");
    try {
      onSignedIn(await (mode === "login" ? auth.login : auth.register)(email, password));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed.");
    }
  };

  return (
    <div style={{ border: "1px solid #999", padding: "1rem", maxWidth: "26rem" }}>
      <h2 style={{ marginTop: 0 }}>Sign in</h2>
      <p style={{ fontSize: "0.9em" }}>
        Your watchlist and review checkpoint live on the server, so the same account shows
        the same state on any device.
      </p>
      <p>
        <input
          type="email"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ width: "100%" }}
        />
      </p>
      <p>
        <input
          type="password"
          placeholder="password (at least 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ width: "100%" }}
        />
      </p>
      <button onClick={() => void submit("login")}>Sign in</button>{" "}
      <button onClick={() => void submit("register")}>Register</button>
      {error && <p style={{ color: "#c33" }}>{error}</p>}
    </div>
  );
}

function Watchlist({
  companies,
  busy,
  onAdd,
  onRemove,
}: {
  companies: WatchedCompany[];
  busy: boolean;
  onAdd: (symbol: string) => void;
  onRemove: (symbol: string) => void;
}) {
  const [symbol, setSymbol] = useState("");
  return (
    <section style={{ margin: "1rem 0" }}>
      <h2>Watchlist</h2>
      {companies.length === 0 ? (
        <p>Nothing watched yet. Add a company to start being told what changed.</p>
      ) : (
        <ul>
          {companies.map((c) => (
            <li key={c.symbol}>
              <strong>{c.symbol}</strong> — {c.company} · coverage {c.coverage_tier} · watched
              from {c.watched_from}{" "}
              <button disabled={busy} onClick={() => onRemove(c.symbol)}>
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        placeholder="symbol, e.g. RELIANCE"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value.toUpperCase())}
      />{" "}
      <button
        disabled={busy || !symbol}
        onClick={() => {
          onAdd(symbol);
          setSymbol("");
        }}
      >
        Add
      </button>
    </section>
  );
}

function ReviewView({
  page,
  busy,
  onComplete,
}: {
  page: ReviewPage;
  busy: boolean;
  onComplete: () => void;
}) {
  return (
    <section style={{ margin: "1rem 0" }}>
      <h2>What changed since you last checked</h2>
      <p style={{ fontSize: "0.9em" }}>
        Window: {page.previous_checkpoint ?? "your first review"} → {page.review_cutoff}
        <br />
        Anything arriving after that cutoff stays new for your next review, even if it
        arrives while you are reading this one.
      </p>

      <p>
        <strong>
          {page.attention_count === 0
            ? "Nothing is asking for your attention."
            : `${page.attention_count} thing${page.attention_count === 1 ? "" : "s"} deserve your attention.`}
        </strong>
      </p>

      <Group title="Changed" lines={page.changed} showAssessments />
      <Group title="Newly added" lines={page.newly_added} />
      <Group title="Could not evaluate reliably" lines={page.unable} />
      <Group title="Quiet" lines={page.quiet} />

      <p>
        <button disabled={busy} onClick={onComplete}>
          Mark review complete
        </button>{" "}
        <span style={{ fontSize: "0.9em" }}>
          Nothing else advances your checkpoint — not opening this page, not refreshing it,
          not leaving it open.
        </span>
      </p>
    </section>
  );
}

function Group({
  title,
  lines,
  showAssessments = false,
}: {
  title: string;
  lines: ReviewLine[];
  showAssessments?: boolean;
}) {
  if (lines.length === 0) return null;
  return (
    <div style={{ margin: "0.75rem 0" }}>
      <h3 style={{ marginBottom: "0.25rem" }}>
        {title} ({lines.length})
      </h3>
      <ul>
        {lines.map((line) => (
          <li key={line.symbol} style={{ marginBottom: "0.4rem" }}>
            <strong>{line.symbol}</strong> — {line.detail}{" "}
            <span style={{ fontSize: "0.85em" }}>(coverage {line.coverage_tier})</span>
            {showAssessments && (
              <ul>
                {line.assessments.map((a) => (
                  <li key={a.event_id}>
                    {attentionLabel(a.attention)} · confidence {a.confidence} ·{" "}
                    {a.corroboration.summary}
                    <br />
                    {a.description}
                    <ul>
                      {a.reasons.map((r) => (
                        <li key={r.code} style={{ fontSize: "0.85em" }}>
                          <code>
                            {r.direction} {r.code}
                          </code>{" "}
                          — {r.detail}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
