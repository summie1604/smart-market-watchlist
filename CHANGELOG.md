# Changelog

## 2026-09-05 — Step 1, market observation

**What:** The deterministic half of the engine. Daily bars from `yfinance` feed a pure
`market` module that runs the D14 chain in the order the design fixes — corporate-action
adjustment, then the security's own trailing baseline, then sector residual, then
unusualness — with each stage taking the previous stage's output so the sequence cannot
be reordered by accident. Market observations become evidence in their own right (D23),
so an unexplained move and a corporate action are both assessable through the existing
event and reason-code path. The disclosure pipeline now consults market data too.

**Why:** Scenarios A and G are the first two the product must get right, and both are
about *not* over-claiming: A refuses to invent a cause for a move nobody can explain, G
refuses to mistake a split for deterioration. Both are proven through the pipeline with
fixtures, not only in the calculation, because the calculation being right does not
prove the product does the right thing with it.

**Corrections found while building:** `TATAMOTORS` no longer resolves — it demerged into
TMPV and TMCV — so the curated universe carried a dead symbol that would have produced a
permanent unexplained coverage gap. The provider's most recent bar carries volume but a
NaN close while the session settles; computing a return against it silently poisons the
baseline, so incomplete sessions are dropped at the adapter. And a corporate action was
initially reported as *unable to evaluate reliably*: the blind→unable promotion fired
because news is missing, even though a split is a complete account of the move it
caused. Self-explaining findings are now exempt, narrowly.

**Open, deliberately:** a 12-sigma unexplained move currently lands at LOW because
`NO_COMPANY_EVENT_DETECTED` nearly cancels `UNUSUAL_PRICE_MOVE`. Whether inexplicability
should demote or promote is a calibration question for a person, not a silent weight
change.

**Rejected:**

- *A per-security assessment unit for market movements.* Two units of assessment and two
  review paths, pre-empting the per-company review page step 4 owes anyway. See D23.
- *Surfacing unusual moves only where a disclosure exists to attach them to.* That is
  scenario A discarded — an unexplained move is a finding.
- *A fixed percentage threshold for unusualness.* Encodes the magnitude-equals-meaning
  error the product exists to reject; baselines are per security.
- *Falling back to the broad index where no sector index is curated.* Would imply a
  comparison we did not make; the residual is `None`, not zero.

## 2026-09-05 — Step 0, the disclosure spike

**What:** The architectural spine, end to end. An authoritative disclosure source (NSE
corporate announcements) travels adapter → evidence → normalization → event candidate →
provenance → the Meaningful Change Engine → persisted assessment → rendered UI. The
engine produces attention levels from signed reason codes over versioned weights, with
confidence tracked as a separate axis, and coverage constraining what a verdict is
allowed to conclude. Three design boundaries the original freeze left unresolved were
recorded as D20–D22.

**Why:** Step 0 existed to prove the architecture and the provenance boundary, not that
an endpoint responds. Building the ugly UI as part of it — rather than deferring all
frontend work to step 6 — was deliberate: a backend model can look elegant in isolation
and turn out awkward to communicate, and the reason-code ledger and coverage states are
exactly the structures that only reveal that when something tries to render them.

**Review-discovered correction, recorded because it is the point of the gate:** the
first implementation attached coverage only to assessments. A zero-evidence or failed
source run therefore produced no assessment to carry it, leaving the previous run's
healthy coverage visible as though it were current — blindness reading as quiet, in the
one component built to demonstrate that the system never does this. It would have
demoed perfectly, because it only appears when the exchange is unreachable. Coverage
moved to run-level persisted state (D20) and the failure path now has focused tests.
Two further defects were caught in the same pass: locale-dependent `%b` date parsing,
which silently dropped every disclosure under a non-English `LC_TIME`, and a test whose
compound assertion short-circuited and could not fail.

**Also settled:** evidence now separates publisher from subject company (D21), so
company identity never derives from whoever published the report; canonical attention
ranking is backend-owned with the frontend rendering the received order (D22); the
frontend API base is configurable through `PUBLIC_API_BASE`; and `IngestRun.is_healthy`
requires a positive coverage record rather than treating an empty set as success.

**Verified:** live slice re-run after the fixes (20 disclosures, 4 MEDIUM, 16 *unable to
evaluate reliably*), the source-failure path exercised explicitly, and the failure
banner confirmed rendering in a browser.

**Rejected:**

- *Storing coverage on assessments only, or inferring source health from the newest
  assessment.* Both leave a failed run invisible — the first has nothing to write to,
  the second lets an old success outlive a new failure. See D20.
- *Calling an LLM in Step 0.* Exchange disclosures arrive already structured, with a
  category and a symbol, so deterministic extraction was both sufficient and more
  honest. The model earns its place in step 2 against free-text news.
- *Deferring the frontend to step 6.* Rejected for the reason above; the cost is an
  interface that stays deliberately ugly through step 5.
- *Fixing `save_run`'s placement after the assessment loop.* Left as-is: SQLite writes
  at this size have no realistic failure path, and the fix belongs with scheduled
  ingestion in step 3.

## 2026-09-05

**What:** Scaffolded the repo — monorepo layout with a Python backend
(`packages/backend`) and an Astro frontend (`packages/web`), the Makefile verb
contract at root and in each package, `AGENTS.md`, an audience-sectioned README,
and `docs/status.md`. `VISION.md` and `DESIGN.md` were written and frozen first.

**Why:** Step 0 of the build is an end-to-end spike through adapter → evidence →
normalization → provenance → engine → assessment → UI. That path crosses both
languages, so both packages had to exist and both had to be green before the spike
could start. Scaffolding first also means `make test` and `aganitha-preflight` have
something real to run against from the first commit rather than the tenth.

**Rejected:** A single-package Python repo with server-rendered templates, which
would have been less setup and one language. Rejected because the review surface —
reason-code ledgers, coverage states, table/card switching, lifecycle timelines —
has genuine interaction state that templates make awkward, and the frontend is half
of what gets judged. Also rejected: deferring the frontend package until step 6.
That risked an engine model that looks elegant in isolation and turns out awkward to
render, which is the failure the ugly Step 0 UI exists to catch early.
