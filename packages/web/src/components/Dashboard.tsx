/**
 * The watchlist interface.
 *
 * Opens on **Needs attention**: what is new since the last completed review, in the order
 * the backend ranked it. The watchlist is the second view, and it always shows the latest
 * known development for every company followed, so an empty attention list is a real
 * answer rather than an empty product.
 *
 * The frontend renders and narrows. It never scores, ranks or re-judges: the order comes
 * from the backend already flattened (D26), attention and confidence are copied as two
 * separate values, coverage is stated as it was recorded, and a contradiction is a link
 * the gates decided (D29). Narrowing — by company, and by the reader's own focus tags —
 * only ever removes rows from view, never changes one.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  auth,
  focusTags as focusTagsApi,
  intelligence,
  judge as judgeApi,
  meta as metaApi,
  prices,
  review as reviewApi,
  universe as universeApi,
  watchPoints as watchPointsApi,
  watchlist as watchlistApi,
  type Account,
  type Assessment,
  type AttentionItem,
  type FocusTagInfo,
  type Interests,
  type Meta,
  type ReviewPage,
  type PriceSession,
  type PriceStatus,
  type UniverseCompany,
  type WatchedCompany,
  type WatchPoint,
} from "../lib/api";
import {
  applyFocus,
  buildRows,
  attentionLabel,
  demandingDevelopments,
  differingVerdicts,
  filterByCompany,
  groupAttentionItems,
  groupedEvidence,
  kindOf,
  needsAttention,
  outsideFocus,
  rowBadge,
  sortRows,
  whenText,
  SORT_LABELS,
  type AttentionGroup,
  type CompanyRow,
  type SortMode,
} from "../lib/rows";
import AddCompany from "./AddCompany";
import Assistant from "./Assistant";

type View = "attention" | "watchlist";
type Phase = "loading" | "ready" | "error";
type Notice = { tone: "ok" | "error"; text: string } | null;

export default function Dashboard() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState("");
  // Needs attention opens first, deliberately. The watchlist is a list of companies; this
  // is the question the product exists to answer, and a reader who lands on a grid of
  // prices has been told the wrong thing about what this is.
  const [view, setView] = useState<View>("attention");
  const [account, setAccount] = useState<Account | null>(null);
  const [companies, setCompanies] = useState<WatchedCompany[]>([]);
  const [supported, setSupported] = useState<UniverseCompany[]>([]);
  const [tagVocabulary, setTagVocabulary] = useState<FocusTagInfo[]>([]);
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [everything, setEverything] = useState<Assessment[]>([]);
  const [priceStatuses, setPriceStatuses] = useState<PriceStatus[]>([]);
  const [company, setCompany] = useState<string | null>(null);
  const [focus, setFocus] = useState<string[]>([]);
  const [sort, setSort] = useState<SortMode>("attention");
  const [points, setPoints] = useState<WatchPoint[]>([]);
  const [serverMeta, setServerMeta] = useState<Meta | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [me, list, all, next, known, vocabulary, priceStatus, levels, server] =
      await Promise.all([
      auth.me(),
      watchlistApi.list(),
      universeApi.list(),
      reviewApi.open(),
      intelligence.all(),
      focusTagsApi.list(),
      prices.status(),
      watchPointsApi.list(),
      metaApi.get(),
    ]);
    setAccount(me);
    setCompanies(list.companies);
    setSupported(all.companies);
    setPage(next);
    setEverything(known.assessments);
    setTagVocabulary(vocabulary.tags);
    setPoints(levels.points);
    setServerMeta(server);
    setPriceStatuses(priceStatus.statuses);
  }, []);

  useEffect(() => {
    refresh()
      .then(() => setPhase("ready"))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Could not reach the API.");
        setPhase("error");
      });
  }, [refresh]);

  const act = async (action: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await action();
      await refresh();
      setNotice({ tone: "ok", text: ok });
    } catch (e: unknown) {
      setNotice({ tone: "error", text: e instanceof Error ? e.message : "Something went wrong." });
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(
    () => (page ? buildRows(companies, page, everything) : []),
    [companies, page, everything],
  );
  const attention = useMemo(() => (page ? needsAttention(page) : []), [page]);
  const shown = useMemo(
    () => applyFocus(filterByCompany(attention, company), focus),
    [attention, company, focus],
  );
  // Sorting reads price figures already in state; it never asks the server for an order
  // and never touches the canonical ranking of developments (D38).
  const visibleRows = useMemo(() => {
    const changeFor = (symbol: string) =>
      priceStatuses.find((item) => item.symbol === symbol)?.daily_change_pct;
    return sortRows(filterByCompany(rows, company), changeFor, sort);
  }, [rows, company, sort, priceStatuses]);
  const openCompany = (symbol: string) => {
    window.location.assign(`/company?symbol=${encodeURIComponent(symbol)}`);
  };

  // Only tags the reader actually chose for a company can be filtered on: offering the
  // whole vocabulary would present filters that can never match as missed news.
  const chosenTags = useMemo(() => {
    const mine = new Set(companies.flatMap((c) => c.tags));
    return tagVocabulary.filter((t) => mine.has(t.tag));
  }, [companies, tagVocabulary]);

  return (
    <>
      {/* Simulated data must never be mistaken for live market information (D42). */}
      {serverMeta?.mode === "judge" && (
        <div className="judge-bar" role="status">
          <span>
            <b>Judge demo</b> · simulated market scenario. Every verdict below was produced
            by the real engine from seeded records — only the market events are simulated.
          </span>
          <button
            type="button"
            className="ghost"
            disabled={busy}
            onClick={() => void act(() => judgeApi.reset(), "Demo scenario restored.")}
          >
            Reset demo
          </button>
        </div>
      )}

      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-name">Smart Market Watchlist</span>
            <span className="brand-sub">
              Know what changed. Know what deserves you.
            </span>
          </div>
          <nav className="nav" aria-label="Views">
            <button
              type="button"
              aria-current={view === "attention"}
              onClick={() => setView("attention")}
            >
              Needs attention
              {attention.length > 0 && <span className="count">{attention.length}</span>}
            </button>
            <button
              type="button"
              aria-current={view === "watchlist"}
              onClick={() => setView("watchlist")}
            >
              Watchlist
            </button>
          </nav>
        </div>
      </header>

      {page && <Strip page={page} rows={rows} />}

      <main className="main">
        {phase === "loading" && <Skeletons />}
        {phase === "error" && (
          <div className="notice error">
            <strong>We couldn’t load your watchlist.</strong> Nothing here is a finding
            about the market — it is our side that is unavailable. Try reloading.
            <span className="notice-detail">{error}</span>
          </div>
        )}

        {phase === "ready" && page && (
          <>
            <p aria-live="polite" className={notice ? `notice ${notice.tone}` : "visually-hidden"}>
              {notice?.text ?? ""}
            </p>

            {/* Orientation first: which view this is, what it contains, and the action
                that closes it. The hero below answers *what changed*; this bar only says
                *what you are looking at*, so the two do not compete. */}
            <section className="lead" aria-label="What this view shows">
              <div>
                <h1>{view === "attention" ? "Needs attention" : "Watchlist"}</h1>
                <p>
                  {view === "watchlist"
                    ? "The latest we know about every company you follow."
                    : page.previous_checkpoint === null
                      ? "Everything since we started watching for you."
                      : `New since your last completed review, ${whenText(page.previous_checkpoint)}.`}
                </p>
              </div>
              {view === "attention" && page.attention_count > 0 && (
                <button
                  type="button"
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      () => reviewApi.complete(page.review_id),
                      "You're caught up. Anything that arrives from now on appears here as new.",
                    )
                  }
                >
                  Mark review complete
                </button>
              )}
            </section>

            {view === "attention" && (
              <WhileYouWereAway
                page={page}
                rows={rows}
                onAcknowledge={(id) =>
                  void act(() => watchPointsApi.acknowledge(id), "Marked as seen.")
                }
                onOpen={openCompany}
              />
            )}

            {/* Controls sit under the answer: a reader should meet what changed before
                meeting the machinery for filtering it. */}
            <AddCompany
              supported={supported}
              watched={companies}
              focusTags={tagVocabulary}
              busy={busy}
              onAdd={(symbol, interests: Interests) =>
                void act(() => watchlistApi.add(symbol, interests), `Now watching ${symbol}.`)
              }
            />

            {companies.length > 0 && (
              <Filters
                companies={companies}
                company={company}
                onCompany={setCompany}
                tags={chosenTags}
                focus={focus}
                onFocus={setFocus}
                showFocus={view === "attention"}
                sort={sort}
                onSort={setSort}
                showSort={view === "watchlist"}
              />
            )}

            {view === "attention" ? (
              <AttentionView
                page={page}
                items={shown.visible}
                keptAnyway={shown.keptAnyway}
                narrowed={shown.narrowed}
                focus={focus}
                rows={visibleRows}
                onOpen={openCompany}
              />
            ) : (
              <WatchlistView
                rows={visibleRows}
                statuses={priceStatuses}
                onRemove={(s) => void act(() => watchlistApi.remove(s), `Stopped watching ${s}.`)}
              />
            )}
          </>
        )}
      </main>

      {/* Watchlist scope: no company context, so questions are answered across the set. */}
      {phase === "ready" && <Assistant />}
    </>
  );
}

/**
 * The first thing a reader sees, and the product's whole argument in one block.
 *
 * Every figure is counted from state already loaded. The order is deliberate: what needs
 * you, then what you asked to be told, then what was genuinely quiet, then how much of
 * your watchlist we could actually evaluate — because the last one is what separates
 * "nothing happened" from "we could not look".
 */
function WhileYouWereAway({
  page,
  rows,
  onAcknowledge,
  onOpen,
}: {
  page: ReviewPage;
  rows: CompanyRow[];
  onAcknowledge: (pointId: string) => void;
  onOpen: (symbol: string) => void;
}) {
  // The same canonical, grouped items the full list renders. No second ordering, no
  // second selection rule — the hero is a shorter view of one answer (D26, D43).
  const demanding = demandingDevelopments(page.needs_attention);
  const triggered = page.triggered_watch_points;
  const quiet = rows.filter((r) => r.state === "quiet").length;
  const unable = rows.filter((r) => r.state === "unable");
  const evaluated = rows.length - unable.length;

  return (
    <section className="away" aria-labelledby="away-heading">
      <div className="away-head">
        <div>
          {/* Both counts this used to headline are stated better a few lines down — as
              "N things need your attention" with the things themselves, and as the
              triggered level with its note. Repeating them as large figures pushed the
              developments below the fold to say nothing new. */}
          <p className="eyebrow">New action items</p>
          <h2 id="away-heading">While you were away</h2>
        </div>
      </div>

      {/* The answer, immediately. A count without the things it counts makes a reader
          hunt for what the product exists to tell them. */}
      {demanding.length > 0 ? (
        <div className="away-answer">
          <h3>
            {demanding.length} {demanding.length === 1 ? "thing needs" : "things need"} your
            attention
          </h3>
          <ul className="previews">
            {demanding.slice(0, 3).map((group) => (
              <li key={group.developmentId}>
                <AttentionPreview group={group} />
              </li>
            ))}
          </ul>
          {demanding.length > 3 && (
            <p className="previews-more">
              {demanding.length - 3} more below.
            </p>
          )}
        </div>
      ) : (
        <div className="away-answer">
          <h3>You're caught up</h3>
          <p className="away-calm">
            Nothing new needs your attention. We looked — that is a finding, not an empty
            page.
          </p>
        </div>
      )}

      {/* A level the reader asked to be told about is a distinct reason for attention and
          is never folded into development grouping (D37, D43). Stated once, here: this is
          the only place the board reports a triggered level, so it carries the two actions
          — open the company, mark it seen — rather than a second section repeating it. */}
      {triggered.length > 0 && (
        <div className="away-asked">
          <h3>
            You asked to be told
            <Hint term="a watch point">
              A price level or percentage move you set yourself. We tell you when an
              end-of-day close reaches it.
            </Hint>
          </h3>
          <ul>
            {triggered.map((point) => (
              <li key={point.point_id}>
                <button
                  type="button"
                  className="asked-open"
                  onClick={() => onOpen(point.symbol)}
                >
                  <span className="asked-what">
                    <b>{point.symbol}</b>{" "}
                    {point.direction === "ABOVE" || point.direction === "PERCENT_UP"
                      ? "reached"
                      : "fell to"}{" "}
                    your level — closed ₹{point.triggered_close?.toLocaleString("en-IN")} on{" "}
                    {point.triggered_on}
                  </span>
                  {point.note && <span className="asked-note">“{point.note}”</span>}
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => onAcknowledge(point.point_id)}
                  aria-label={`Mark the ${point.symbol} level as seen`}
                >
                  got it
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Operational state, supporting the answer rather than being it. */}
      <p className="away-status">
        <span>
          <b>{triggered.length}</b> watch{" "}
          {triggered.length === 1 ? "point" : "points"} triggered
        </span>
        <span>
          <b>{quiet}</b> quiet
        </span>
        <span data-tone={unable.length > 0 ? "degraded" : undefined}>
          <b>
            {evaluated}/{rows.length}
          </b>{" "}
          evaluated
          <Hint term="evaluated">
            How many of the companies you follow we could check this time. A source being
            down does not make a company quiet.
          </Hint>
        </span>
      </p>

      {unable.length > 0 && (
        <p className="away-degraded">
          <b>
            {unable.map((r) => r.symbol).join(", ")} could not be evaluated.
          </b>{" "}
          A source was unavailable, so silence there is ours and not the market's.
        </p>
      )}

      <HowItWorks />
    </section>
  );
}

/**
 * One development, compact enough to read at a glance.
 *
 * Orientation, not the full card: company, what happened, how important, and one line of
 * why. The complete record — reason-code arithmetic, every source, related updates — is
 * the card below, which this links to rather than duplicating.
 */
function AttentionPreview({ group }: { group: AttentionGroup }) {
  const { symbol, company, assessment } = group.primary;

  return (
    <article className="preview" data-tone={assessment.attention}>
      <p className="preview-head">
        <span className="attn-level" data-tone={assessment.attention}>
          {attentionLabel(assessment.attention)}
        </span>
        <b className="preview-sym">{symbol}</b>
        <span className="preview-co">{company}</span>
        <span className="preview-when">{whenText(assessment.occurred_at)}</span>
      </p>

      <p className="preview-what">{assessment.description}</p>

      {/* The two supporting axes, in words, subordinate to the level above. */}
      <p className="preview-why">
        {assessment.source_standing_label}
        {group.sources > 0 && (
          <>
            {" · "}
            {group.sources} independent {group.sources === 1 ? "source" : "sources"}
          </>
        )}
        {" · "}
        {assessment.confidence.toLowerCase()} confidence
        {group.related.length > 0 && <> · {group.related.length + 1} related records</>}
      </p>

      <a className="preview-link" href={`#development-${group.developmentId}`}>
        Why this matters
        <span className="visually-hidden"> — {symbol}, {assessment.description}</span>
        <span aria-hidden="true"> →</span>
      </a>
    </article>
  );
}

/**
 * The reasoning chain, in one line, expandable.
 *
 * Present because the interesting claim — that a model extracts and rules decide — is
 * invisible in a list of verdicts. Deliberately not a marketing page: five steps, no
 * illustration, closed by default.
 */
function HowItWorks() {
  const [open, setOpen] = useState(false);
  return (
    <div className="how">
      <button type="button" className="how-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        How this decides what deserves you
      </button>
      {open && (
        <ol className="how-steps">
          <li>
            <b>Observe</b> Prices, NSE disclosures and reporting, on a schedule — never on a
            page view.
          </li>
          <li>
            <b>Establish evidence</b> Each record keeps its publisher, source standing and
            timestamps. What we could not consult is recorded too.
          </li>
          <li>
            <b>Evaluate</b> Deterministic reason codes, each with a signed contribution. A
            language model extracts structure from articles; it never decides significance.
          </li>
          <li>
            <b>Rank</b> Attention and confidence stay separate axes — how much it matters is
            not how sure we are.
          </li>
          <li>
            <b>Explain</b> Every verdict can produce the reason codes that made it. One that
            cannot be explained cannot be ranked.
          </li>
        </ol>
      )}
    </div>
  );
}

/* --- narrowing controls ---------------------------------------------------- */

function Filters({
  companies,
  company,
  onCompany,
  tags,
  focus,
  onFocus,
  showFocus,
  sort,
  onSort,
  showSort,
}: {
  companies: WatchedCompany[];
  company: string | null;
  onCompany: (symbol: string | null) => void;
  tags: FocusTagInfo[];
  focus: string[];
  onFocus: (tags: string[]) => void;
  showFocus: boolean;
  sort: SortMode;
  onSort: (mode: SortMode) => void;
  showSort: boolean;
  /** Focus narrows *developments*, so it only appears where developments are listed.
   *
   * On the watchlist it did nothing at all — the rows are companies, and the filter never
   * touched them. A control that looks like it works and does not is worse than no
   * control: it teaches the reader that filtering is broken. */
}) {
  return (
    <div className="filters">
      <div className="filter">
        <label htmlFor="company-filter">Company</label>
        <select
          id="company-filter"
          value={company ?? ""}
          onChange={(e) => onCompany(e.target.value === "" ? null : e.target.value)}
        >
          <option value="">All companies</option>
          {companies.map((c) => (
            <option key={c.symbol} value={c.symbol}>
              {c.symbol} — {c.company}
            </option>
          ))}
        </select>
      </div>

      {/* Sorting arranges companies; focus narrows developments. Each appears only on the
          view where it does something. */}
      {showSort && (
        <div className="filter">
          <label htmlFor="sort-mode">Sort</label>
          <select
            id="sort-mode"
            value={sort}
            onChange={(event) => onSort(event.target.value as SortMode)}
          >
            {(Object.keys(SORT_LABELS) as SortMode[]).map((mode) => (
              <option key={mode} value={mode}>
                {SORT_LABELS[mode]}
              </option>
            ))}
          </select>
        </div>
      )}

      {showFocus && tags.length > 0 && (
        <div className="filter">
          <span id="focus-label">Focus</span>
          <div className="chips" role="group" aria-labelledby="focus-label">
            {tags.map((tag) => {
              const on = focus.includes(tag.tag);
              return (
                <button
                  key={tag.tag}
                  type="button"
                  className="chip"
                  aria-pressed={on}
                  onClick={() =>
                    onFocus(on ? focus.filter((t) => t !== tag.tag) : [...focus, tag.tag])
                  }
                >
                  {tag.label}
                </button>
              );
            })}
            {focus.length > 0 && (
              <button type="button" className="chip clear" onClick={() => onFocus([])}>
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* --- views ------------------------------------------------------------------ */

function AttentionView({
  page,
  items,
  keptAnyway,
  narrowed,
  focus,
  rows,
  onOpen,
}: {
  page: ReviewPage;
  items: AttentionItem[];
  keptAnyway: number;
  narrowed: number;
  focus: string[];
  rows: CompanyRow[];
  onOpen: (symbol: string) => void;
}) {
  return (
    <>
      {narrowed > 0 && (
        <p className="notice">
          {narrowed} lower-attention {narrowed === 1 ? "development is" : "developments are"}{" "}
          hidden by your focus. Clear it to see everything.
        </p>
      )}

      {items.length === 0 ? (
        <div className="blank">
          <h2>Nothing new needs you</h2>
          <p>
            {page.attention_count > 0
              ? "Nothing matches the filters you have applied. Everything else is below."
              : "That is an answer, not an empty page — we looked, and nothing on your watchlist meaningfully changed."}
          </p>
        </div>
      ) : (
        <ul className="attn-rows">
          {/* Grouped for reading, never for record-keeping: every underlying assessment is
              still here, one expand away, with its own verdict and reasoning (D43). */}
          {groupAttentionItems(items).map((group) => (
            <li key={group.developmentId}>
              <AttentionRow group={group} focus={focus} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}

      {keptAnyway > 0 && (
        <p className="footnote">
          {keptAnyway} high-attention {keptAnyway === 1 ? "development" : "developments"} shown
          despite falling outside your focus.
        </p>
      )}

      <RestOfWatchlist rows={rows} onOpen={onOpen} />
    </>
  );
}

/**
 * One thing that needs the reader.
 *
 * Attention dominates; confidence and source standing sit under it as supporting facts,
 * because they answer different questions and giving all three equal weight is what makes
 * three axes read as decoration.
 *
 * "Why you're seeing this" opens the engine's own reason-code ledger — the signed
 * contributions that produced the level. Nothing here is generated: each line is a
 * `ReasonCode.detail` the engine emitted when it made the decision.
 */
/**
 * A one-sentence explanation of a term a first-time reader will not know.
 *
 * Used only for the vocabulary this product actually invents — attention, confidence,
 * source standing, coverage — never for words like "price" that explain themselves. It is
 * a button rather than a hover target so that a keyboard reader and a touch reader can
 * both reach it; the panel is shown by `:focus-within`, so there is no open state to
 * manage and none to leave stuck.
 */
function Hint({ term, children }: { term: string; children: string }) {
  return (
    <span className="hint">
      <button type="button" className="hint-dot" aria-label={`What does ${term} mean?`}>
        <span aria-hidden="true">i</span>
      </button>
      <span className="hint-body" role="tooltip">
        {children}
      </span>
    </span>
  );
}

function AttentionRow({
  group,
  focus,
  onOpen,
}: {
  group: AttentionGroup;
  focus: string[];
  onOpen: (symbol: string) => void;
}) {
  const [why, setWhy] = useState(false);
  const [updates, setUpdates] = useState(false);
  const { symbol, company, assessment } = group.primary;
  const supporting = assessment.reasons.filter((r) => r.direction === "+");
  const against = assessment.reasons.filter((r) => r.direction === "-");

  return (
    <article
      className="attn-row"
      id={`development-${group.developmentId}`}
      data-tone={assessment.attention}
    >
      <div className="attn-main">
        <div className="attn-head">
          <span className="attn-level" data-tone={assessment.attention}>
            {attentionLabel(assessment.attention)}
          </span>
          <Hint term="attention">
            How much this development deserves your time, judged from the evidence — not
            from the size of the price move.
          </Hint>
          <button type="button" className="attn-open" onClick={() => onOpen(symbol)}>
            <span className="tile-sym">{symbol}</span>
            <span className="tile-co">{company}</span>
          </button>
        </div>

        <p className="tile-dev">{assessment.description}</p>

        {/* Supporting, not competing: one line, small, after the development itself. */}
        <p className="attn-axes">
          <span>
            Confidence · <b>{assessment.confidence.toLowerCase()}</b>
            <Hint term="confidence">
              How strongly the evidence we have supports this reading. It is separate from
              how much the development matters.
            </Hint>
          </span>
          <span>
            Source · <b>{assessment.source_standing_label}</b>
            <Hint term="source standing">
              Who reported it. An exchange filing is the company itself; an established
              outlet is a newsroom we recognise.
            </Hint>
          </span>
          {/* Across the development, counted by the backend so a grouped card cannot
              overstate its corroboration. Omitted at zero: our own market measurement has
              no publisher, and "0 independent sources" reads as a failing rather than as
              a computed observation (D13). */}
          {group.sources > 0 && (
            <span>
              {group.sources} independent {group.sources === 1 ? "source" : "sources"}
            </span>
          )}
          <span>{whenText(assessment.occurred_at)}</span>
        </p>

        {assessment.focus.length > 0 && (
          <p className="matched">
            Matches your focus: {assessment.focus.map((m) => m.label).join(", ")}
          </p>
        )}
        {outsideFocus(assessment, focus) && (
          <p className="matched outside">Outside your focus — we think it matters anyway</p>
        )}
        {assessment.contradiction.confirmed && (
          <p className="matched disputed">
            {assessment.contradiction.state === "WITHDRAWN" ? "Withdrawn" : "Disputed"} by a
            later report
          </p>
        )}

        <div className="attn-actions">
          <button
            type="button"
            className="why-toggle"
            aria-expanded={why}
            onClick={() => setWhy(!why)}
          >
            {why ? "Hide reasoning" : "Why you're seeing this"}
          </button>

          {group.related.length > 0 && (
            <button
              type="button"
              className="why-toggle"
              aria-expanded={updates}
              onClick={() => setUpdates(!updates)}
            >
              {updates ? "Hide updates" : `${group.related.length} related`}
              <span className="visually-hidden">
                {" "}
                {group.related.length === 1 ? "record" : "records"} for this development
              </span>
            </button>
          )}
        </div>

        {updates && (
          <ol className="attn-updates">
            {group.related.map((item) => (
              <li key={item.assessment.event_id}>
                <span className="upd-when">{whenText(item.assessment.occurred_at)}</span>
                {/* A related record whose verdict differs is development history, not
                    noise to hide. */}
                {item.assessment.attention !== assessment.attention && (
                  <span className="badge" data-tone={item.assessment.attention}>
                    {attentionLabel(item.assessment.attention)}
                  </span>
                )}
                <span className="upd-what">{item.assessment.description}</span>
                <span className="src-standing">{item.assessment.source_standing_label}</span>
              </li>
            ))}
          </ol>
        )}

        {why && (
          <div className="why-panel">
            <ol className="why-list">
              {supporting.map((reason) => (
                <li key={reason.code} data-direction="+">
                  <span className="why-weight">+{reason.contribution}</span>
                  {reason.detail}
                </li>
              ))}
              {against.map((reason) => (
                <li key={reason.code} data-direction="-">
                  <span className="why-weight">{reason.contribution}</span>
                  {reason.detail}
                </li>
              ))}
            </ol>
            <p className="why-verdict">
              Scored {assessment.score} by {assessment.scoring_version} →{" "}
              <b>{attentionLabel(assessment.attention)}</b>, at{" "}
              <b>{assessment.confidence.toLowerCase()}</b> confidence.
            </p>
            {groupedEvidence(group).length > 0 && (
              <ul className="why-sources">
                {groupedEvidence(group)
                  .slice(0, 5)
                  .map((evidence) => (
                  <li key={evidence.ref}>
                    {evidence.publisher || evidence.source}{" "}
                    <span className="src-standing">{evidence.standing_label}</span>
                    {evidence.url && (
                      <>
                        {" · "}
                        <a href={evidence.url} target="_blank" rel="noreferrer">
                          source
                        </a>
                      </>
                      )}
                    </li>
                  ))}
              </ul>
            )}
            {differingVerdicts(group) && (
              <p className="why-verdict">
                Earlier records for this development reached a different level. Each keeps
                its own verdict and reasoning; nothing was combined.
              </p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

/**
 * The rest of the watchlist, always present under the attention list.
 *
 * This is what keeps an empty attention list from being an empty screen: the latest we
 * know about every company, which companies were genuinely quiet, and which we could not
 * evaluate. The third group is the one that must never be folded into the second — "we
 * looked and nothing happened" and "we could not look" are different answers (D15).
 */
function RestOfWatchlist({
  rows,
  onOpen,
}: {
  rows: CompanyRow[];
  onOpen: (symbol: string) => void;
}) {
  // Keyed on the backend's own verdict for each company, because these three are
  // different answers and only it knows which applies. Every row still carries the most
  // recent development we hold, so no section is a list of bare names.
  const resting = rows.filter((r) => r.newCount === 0);
  const quiet = resting.filter((r) => r.state === "quiet");
  const latest = resting.filter((r) => r.state !== "quiet" && r.state !== "unable");
  const unable = rows.filter((r) => r.state === "unable");

  if (rows.length === 0) {
    return (
      <div className="blank">
        <h2>Your watchlist is empty</h2>
        <p>
          Add a company above. From then on this screen answers one question: what changed
          while you were away, and does it deserve you?
        </p>
      </div>
    );
  }

  return (
    <div className="rest">
      <Group
        title="Quiet"
        note="We looked and nothing meaningful changed. Below is the most recent thing we hold for each."
        rows={quiet}
        onOpen={onOpen}
        showLatest
      />
      <Group
        title="Latest we know"
        note="Nothing inside your review window; this is the most recent development on record."
        rows={latest}
        onOpen={onOpen}
        showLatest
      />
      <Group
        title="Could not evaluate"
        note="A source was unavailable, so silence here is ours and not the market's."
        rows={unable}
        onOpen={onOpen}
        tone="warn"
      />
    </div>
  );
}

function Group({
  title,
  note,
  rows,
  onOpen,
  showLatest = false,
  tone,
}: {
  title: string;
  note: string;
  rows: CompanyRow[];
  onOpen: (symbol: string) => void;
  showLatest?: boolean;
  tone?: "warn";
}) {
  if (rows.length === 0) return null;
  return (
    <section className="rest-group" data-tone={tone}>
      <div className="group-head">
        <h2>{title}</h2>
        <span className="n">{rows.length}</span>
      </div>
      <p className="group-note">{note}</p>
      <ul className="rest-rows">
        {rows.map((row) => (
          <li key={row.symbol}>
            <button type="button" className="rest-row" onClick={() => onOpen(row.symbol)}>
              <span className="tile-sym">{row.symbol}</span>
              <span className="rest-text">
                {showLatest && row.latest !== null ? row.latest.description : row.detail}
              </span>
              <span className="rest-when">
                {showLatest && row.latest !== null ? whenText(row.latest.occurred_at) : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function WatchlistView({
  rows,
  statuses,
  onRemove,
}: {
  rows: CompanyRow[];
  statuses: PriceStatus[];
  onRemove: (symbol: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <div className="blank">
        <h2>Nothing to show</h2>
        <p>Add a company above, or clear the company filter.</p>
      </div>
    );
  }

  return (
    <>
      <div className="tiles">
        {rows.map((row, index) => (
          <Tile
            key={row.symbol}
            row={row}
            rank={index + 1}
            status={statuses.find((item) => item.symbol === row.symbol)}
            onRemove={onRemove}
          />
        ))}
      </div>
    </>
  );
}

function Tile({
  row,
  rank,
  status,
  onRemove,
}: {
  row: CompanyRow;
  rank: number;
  status: PriceStatus | undefined;
  onRemove: (s: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const badge = rowBadge(row);
  // Leads with what is new if anything is, otherwise the most recent thing we know — a
  // company is never shown blank just because today was quiet.
  const shown = row.headline ?? row.latest;

  return (
    <article className="tile" data-tone={badge.tone} data-expanded={expanded}>
      {/* One real link, stretched over the whole card by CSS.
       *
       * A link rather than a click handler so the card behaves like a link everywhere it
       * matters: middle-click, ctrl-click and "open in new tab" all work, and the status
       * bar shows the destination on hover. A screen reader gets one clear target named
       * for the company rather than a target per line.
       *
       * Controls that are not "open this company" — the trace, the expander, remove, and
       * the expanded text itself — sit above the overlay and keep their own behaviour. */}
      <a className="tile-link" href={`/company?symbol=${encodeURIComponent(row.symbol)}`}>
        <span className="rank">{rank}</span>
        <span className="tile-sym">{row.symbol}</span>
        {/* The verdict sits with the name, because it is the reason this card exists.
            Price follows the development rather than leading it (D2). */}
        <span className="badge" data-tone={badge.tone}>
          {badge.label}
        </span>
        <span className="tile-co">{row.company}</span>
      </a>

      <div className="tile-body">
        {shown ? (
          <p className="tile-dev">{shown.description}</p>
        ) : (
          <p className="tile-dev none">{row.detail || "Nothing recorded for this company yet."}</p>
        )}
      </div>

      <PriceStatusLine status={status} symbol={row.symbol} />

      <div className="tile-stats">
        <span>{shown ? whenText(shown.occurred_at) : "—"}</span>
        {shown && <span>{shown.corroboration.summary}</span>}
        {row.newCount > 0 && <span>{row.newCount} new</span>}
        {row.coverageTier === "LIMITED" && <span>limited coverage</span>}
        {row.state === "unable" && <span>sources unavailable</span>}
      </div>

      {/* Expanding reads more of the record in place. The board is where a reader decides
          what to open, and making them open a page to find out whether it is worth
          opening is the wrong way round. */}
      {shown && (
        <button
          type="button"
          className="tile-more"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Less" : "Why this is here"}
        </button>
      )}

      {expanded && shown && (
        <div className="tile-detail">
          <p className="tile-full">{shown.description}</p>
          <ul>
            {shown.reasons.slice(0, 4).map((reason) => (
              <li key={reason.code} className={reason.direction === "-" ? "against" : ""}>
                {reason.detail}
              </li>
            ))}
          </ul>
          <p className="tile-sources">
            {[...new Set(shown.evidence.map((e) => e.publisher))].slice(0, 4).join(", ") ||
              "no publisher recorded"}
          </p>
        </div>
      )}

      <div className="tile-foot">
        {shown && (
          <span className="badge soft">{shown.confidence.toLowerCase()} confidence</span>
        )}
        {shown && (
          <span className="badge standing" data-standing={shown.source_standing}>
            {shown.source_standing_label}
          </span>
        )}
        <button
          type="button"
          className="ghost"
          onClick={() => onRemove(row.symbol)}
          aria-label={`Stop watching ${row.symbol}`}
        >
          remove
        </button>
      </div>
    </article>
  );
}

function PriceStatusLine({
  status,
  symbol,
}: {
  status: PriceStatus | undefined;
  symbol: string;
}) {
  if (status?.close === null || status?.close === undefined) {
    return (
      <p className="price-status unavailable">Price unavailable — no stored end-of-day close yet.</p>
    );
  }
  const change = status.daily_change_pct;
  const absolute = status.daily_change;
  return (
    <div className="price-status">
      <span className="price">
        ₹{status.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
      </span>
      {change !== null && change !== undefined ? (
        <span className={change >= 0 ? "move up" : "move down"}>
          {/* One sign, applied to both figures. They are the same fact in two units, so an
              unsigned rupee move beside a negative percentage reads as a contradiction. */}
          {absolute !== null && absolute !== undefined
            ? `${change >= 0 ? "+" : "−"}₹${Math.abs(absolute).toLocaleString("en-IN", {
                maximumFractionDigits: 2,
              })} `
            : ""}
          ({change >= 0 ? "+" : "−"}
          {Math.abs(change).toFixed(2)}%)
        </span>
      ) : (
        <span className="move">Daily move unavailable</span>
      )}
      <Sparkline sessions={status.sessions} symbol={symbol} />
      <span className="as-of">
        EOD {status.as_of ?? "—"}
        {/* Only rendered where the provider gave a range. A high copied from the close
            would be a fabricated session. */}
        {status.day_high !== null && status.day_low !== null && (
          <>
            {" · "}day {status.day_low?.toLocaleString("en-IN")}–
            {status.day_high?.toLocaleString("en-IN")}
          </>
        )}
        {status.day_volume ? <> · vol {compactNumber(status.day_volume)}</> : null}
      </span>
    </div>
  );
}

/** Large counts, readably. Formatting only — the value is the provider's. */
export function compactNumber(value: number): string {
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)} cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)} lakh`;
  return value.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

/**
 * The stored end-of-day trace, readable rather than decorative.
 *
 * Pointing at it names the session and its close — both stored values, neither computed
 * here. It reads on every surface: pointer, touch and keyboard all move the same
 * selection, and the selected session is announced rather than only drawn, so the chart
 * is not the only way to get the number.
 */
function Sparkline({ sessions, symbol }: { sessions: PriceSession[]; symbol: string }) {
  const [active, setActive] = useState<number | null>(null);
  if (sessions.length < 2) return null;

  const closes = sessions.map((s) => s.close);
  const low = Math.min(...closes);
  const span = Math.max(...closes) - low || 1;
  const at = (index: number) => ({
    x: (index / (sessions.length - 1)) * 100,
    y: 24 - ((sessions[index]!.close - low) / span) * 24,
  });
  const path = sessions
    .map((_, index) => {
      const { x, y } = at(index);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // The pointer position maps to the nearest stored session — never to a value between
  // two of them, because there is no such session and inventing one is a fabricated price.
  const select = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width === 0) return;
    const ratio = (event.clientX - box.left) / box.width;
    const index = Math.round(ratio * (sessions.length - 1));
    setActive(Math.min(Math.max(index, 0), sessions.length - 1));
  };

  const selected = active === null ? null : sessions[active]!;

  return (
    <span className="spark-wrap">
      <svg
        className="sparkline"
        viewBox="0 0 100 24"
        preserveAspectRatio="none"
        role="img"
        aria-label={`${sessions.length} stored end-of-day closes for ${symbol}`}
        tabIndex={0}
        onPointerDown={select}
        onPointerMove={(event) => {
          if (event.buttons > 0 || event.pointerType === "mouse") select(event);
        }}
        onPointerLeave={() => setActive(null)}
        onBlur={() => setActive(null)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          event.preventDefault();
          const step = event.key === "ArrowRight" ? 1 : -1;
          const from = active ?? sessions.length - 1;
          setActive(Math.min(Math.max(from + step, 0), sessions.length - 1));
        }}
      >
        <path d={path} />
        {active !== null && (
          <circle className="spark-dot" cx={at(active).x} cy={at(active).y} r={2.5} />
        )}
      </svg>
      {selected && (
        <output className="spark-read">
          ₹{selected.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })} on{" "}
          {selected.on}
        </output>
      )}
    </span>
  );
}

/**
 * Coverage and freshness across the board — the honest equivalent of a market snapshot.
 *
 * Every figure is counted from state already loaded for this page. None of it is stored,
 * because all of it is cheaper to count than to keep correct.
 */
function Strip({ page, rows }: { page: ReviewPage; rows: CompanyRow[] }) {
  const degraded = rows.filter((r) => r.state === "unable").length;
  const quiet = rows.filter((r) => r.state === "quiet").length;
  const surfaced = page.needs_attention;
  const significant = surfaced.filter(
    (item) => item.assessment.attention === "HIGH" || item.assessment.attention === "MEDIUM",
  ).length;
  // Counted from the evidence behind each item, the same way the detail groups them.
  const disclosures = surfaced.filter((item) => kindOf(item.assessment) === "disclosure").length;
  const alerts = page.triggered_watch_points.length;

  return (
    <div className="strip">
      <div className="strip-inner">
        <span>
          <b>Watching</b> {rows.length}
        </span>
        <span>
          <b>New</b> <span className={page.attention_count > 0 ? "ok" : ""}>{page.attention_count}</span>
        </span>
        <span>
          <b>Needs you</b> <span className={significant > 0 ? "ok" : ""}>{significant}</span>
        </span>
        <span>
          <b>Filings</b> {disclosures}
        </span>
        <span>
          <b>Your alerts</b> <span className={alerts > 0 ? "ok" : ""}>{alerts}</span>
        </span>
        <span>
          <b>Quiet</b> {quiet}
        </span>
        <span>
          <b>Not checked</b> <span className={degraded > 0 ? "bad" : ""}>{degraded}</span>
        </span>
        <span>
          <b>Since</b>{" "}
          {page.previous_checkpoint ? whenText(page.previous_checkpoint) : "first review"}
        </span>
      </div>
    </div>
  );
}

function Skeletons() {
  return (
    <div className="loading" aria-busy="true">
      <p className="visually-hidden" role="status">
        Loading what changed since your last review.
      </p>
      {/* Shaped like the hero and the first two developments, so the page does not
          reflow when the answer arrives — and so nothing here can be misread as a
          count of zero. */}
      <div className="skeleton skeleton-lead" />
      <div className="skeleton skeleton-hero" />
      <div className="skeleton skeleton-card" />
      <div className="skeleton skeleton-card" />
    </div>
  );
}
