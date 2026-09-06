/**
 * The assistant drawer — a conversational way into the system's own intelligence (D40).
 *
 * Every answer is composed server-side from records the engine already produced. This
 * component sends a question and renders what comes back: it does not summarise, rephrase,
 * soften a refusal or fill a gap, because doing any of those would make the client a
 * second, ungoverned explanation path.
 *
 * The transcript is session-only and lives in this component's state. Nothing is
 * persisted, because each answer is composed independently from the stored record — there
 * is no conversational memory to keep, and pretending otherwise would suggest the
 * assistant is reasoning across turns when it is not.
 */

import { useEffect, useRef, useState } from "react";
import { assistant, type AssistantAnswer } from "../lib/api";

interface Turn {
  question: string;
  answer: AssistantAnswer | null;
  error: string | null;
}

/** Contextual openers. The server returns its own set with every reply. */
const OPENERS = {
  watchlist: [
    "What needs my attention?",
    "What are my biggest movers?",
    "Any important new disclosures?",
    "What alerts have triggered?",
  ],
  company: [
    "Why is this getting attention?",
    "What happened recently?",
    "What evidence do we have?",
    "Explain this in simple terms",
  ],
} as const;

export default function Assistant({ symbol }: { symbol?: string }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  /** Closing returns focus where it came from, so a keyboard reader is not dropped on
   *  `<body>` and left to tab back through the whole page. */
  const close = () => {
    setOpen(false);
    opener.current?.focus();
  };

  useEffect(() => {
    // Newest turn in view. `scrollTop` rather than `scrollIntoView` so opening the panel
    // never scrolls the page behind it.
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [turns, busy]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = (text: string) => {
    const asked = text.trim();
    if (asked === "" || busy) return;
    setQuestion("");
    setBusy(true);
    assistant
      .ask(asked, symbol)
      .then((answer) => setTurns((prior) => [...prior, { question: asked, answer, error: null }]))
      .catch((reason: unknown) =>
        setTurns((prior) => [
          ...prior,
          {
            question: asked,
            answer: null,
            error: reason instanceof Error ? reason.message : "The question could not be answered.",
          },
        ]),
      )
      .finally(() => setBusy(false));
  };

  const openers = symbol ? OPENERS.company : OPENERS.watchlist;

  return (
    <>
      <button
        type="button"
        ref={opener}
        className="assistant-open"
        aria-expanded={open}
        aria-label={open ? "Close the assistant" : symbol ? `Ask about ${symbol}` : "Ask about your watchlist"}
        onClick={() => (open ? close() : setOpen(true))}
      >
        {open ? "Close" : symbol ? `Ask about ${symbol}` : "Ask about your watchlist"}
      </button>

      {open && (
        <aside className="assistant" role="dialog" aria-label="Ask about your watchlist">
          <div className="assistant-head">
            <div>
              <h2>{symbol ? `Ask about ${symbol}` : "Ask about your watchlist"}</h2>
              <p>
                {symbol
                  ? `Answered from what we have assessed for ${symbol}.`
                  : "Answered from what we have assessed for your watchlist."}
              </p>
            </div>
            {turns.length > 0 && (
              <button type="button" className="ghost" onClick={() => setTurns([])}>
                clear
              </button>
            )}
            {/* A close control inside the panel. On a phone the panel is a bottom sheet
                that covers the floating button, and there is no Escape key — without this
                the drawer could be opened and not closed. */}
            <button type="button" className="ghost assistant-close" onClick={close}>
              close
            </button>
          </div>

          {/* Answers are announced as they arrive. Without this the panel is silent to a
              screen reader: the busy message was the only thing being read out. */}
          <div className="assistant-log" ref={log} role="log" aria-live="polite">
            {turns.length === 0 && (
              <p className="assistant-empty">
                I can explain what the system already found — why something is flagged, what
                evidence sits behind it, and what it could not see. I do not give advice or
                predict prices.
              </p>
            )}

            {turns.map((turn, index) => (
              <div className="turn" key={`${index}-${turn.question}`}>
                <p className="asked">
                  <span className="speaker">You</span>
                  {turn.question}
                </p>
                {turn.error !== null ? (
                  <div className="notice error">
                    <p>{turn.error}</p>
                    {/* The question is still in hand, so retrying costs the reader nothing
                        — a failed request should not make them type it again. */}
                    <button
                      type="button"
                      className="retry"
                      disabled={busy}
                      onClick={() => {
                        setTurns((prior) => prior.filter((_, at) => at !== index));
                        send(turn.question);
                      }}
                    >
                      Try again
                    </button>
                  </div>
                ) : (
                  turn.answer && (
                    <>
                      <p className="speaker answered">From the record</p>
                      <AnswerBlock answer={turn.answer} onAsk={send} />
                    </>
                  )
                )}
              </div>
            ))}

            {busy && (
              <p className="assistant-busy" aria-live="polite">
                Reading the record…
              </p>
            )}
          </div>

          {/* Kept after the first answer, not only before it. Most follow-up questions are
              another one of these, and hiding them made the panel harder to use the longer
              it was open. */}
          <ul className="assistant-openers">
            {openers.map((suggestion) => (
              <li key={suggestion}>
                <button
                  type="button"
                  className="chip"
                  disabled={busy}
                  onClick={() => send(suggestion)}
                >
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>

          <form
            className="assistant-form"
            onSubmit={(event) => {
              event.preventDefault();
              send(question);
            }}
          >
            <label className="visually-hidden" htmlFor="assistant-question">
              Ask a question
            </label>
            <input
              id="assistant-question"
              ref={input}
              type="text"
              maxLength={300}
              autoComplete="off"
              placeholder={symbol ? "Why is this getting attention?" : "What needs my attention?"}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <button type="submit" className="primary" disabled={busy}>
              Send
            </button>
          </form>
        </aside>
      )}
    </>
  );
}

/**
 * One answer, rendered exactly as the server composed it.
 *
 * The window, the coverage gap and the citation under each statement are what make the
 * answer checkable, so none of them is optional decoration.
 */
function AnswerBlock({
  answer,
  onAsk,
}: {
  answer: AssistantAnswer;
  onAsk: (question: string) => void;
}) {
  const cited = new Map(answer.evidence.map((item) => [item.ref, item]));

  return (
    <div className="answer" data-answered={answer.answered}>
      <p className="answer-window">
        {answer.scope === "company" && answer.symbol ? `${answer.symbol} · ` : ""}
        {answer.window.basis} · {answer.window.assessments_considered}{" "}
        {answer.window.assessments_considered === 1 ? "assessment" : "assessments"} considered
      </p>

      {!answer.coverage.complete && (
        <p className="answer-gap">
          Coverage gap — {answer.coverage.note}. Anything those sources would have shown is
          missing from this answer.
        </p>
      )}

      <ul className="answer-statements">
        {answer.statements.map((statement, index) => (
          <li key={`${index}-${statement.text.slice(0, 24)}`}>
            {statement.text}
            {statement.event_ids.length > 0 && (
              <span className="answer-cite">
                {" "}
                ({statement.event_ids.length}{" "}
                {statement.event_ids.length === 1 ? "record" : "records"})
              </span>
            )}
          </li>
        ))}
      </ul>

      {cited.size > 0 && (
        <details className="answer-evidence">
          <summary>Evidence ({cited.size})</summary>
          <ul className="sources">
            {[...cited.values()].map((evidence) => (
              <li key={evidence.ref}>
                {evidence.publisher || evidence.source}{" "}
                {/* The product's one source-standing vocabulary (D36), not a second one
                    invented for chat. */}
                <span className="src-standing">{evidence.standing_label}</span>
                {evidence.url && (
                  <>
                    {" · "}
                    <a href={evidence.url} target="_blank" rel="noreferrer">
                      read the source
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {!answer.answered && answer.suggestions.length > 0 && (
        <ul className="assistant-openers">
          {answer.suggestions.slice(0, 4).map((suggestion) => (
            <li key={suggestion}>
              <button type="button" className="chip" onClick={() => onAsk(suggestion)}>
                {suggestion}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
