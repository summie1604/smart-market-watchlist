# Changelog

## 2026-09-05 — Step 2 acceptance: the full 21-article evaluation

**What:** The evaluation that was left at 11 of 21 calls is complete. All 21 fixture cases
now have genuine Gemini outcomes: **14 true positives, 7 true negatives, 0 false
positives, 0 false negatives** — 100% precision and recall, no unusable responses, no
quota failures in the final set. Three grounding rejections removed a `contract_value` and
two `regulator` fields the sources did not support.

**How the remaining cases were run:** the ten quota-blocked cases were rerun, plus
`leadership-change`, whose earlier `unusable-response` was caused by the output-truncation
defect fixed after that run — its old outcome was no longer comparable. The free tier
caps requests at 20 per model per day, so the 21 outcomes span three sibling flash models:
17 on `gemini-3-flash-preview`, 2 on `gemini-flash-latest`, 2 on `gemini-3.1-flash-lite`.
D25 treats the model revision as deployment configuration rather than a domain contract,
which is what makes that acceptable — but these are Gemini-family figures, not one
model's.

**Defect found and fixed:** `leadership-change` returned `contract_value` as the literal
string `"null"`. Grounding dropped it, but only because that word was absent from the
source — `"unknown"` and `"none"` do appear in real articles, so the guarantee rested on
an accident. Sentinel strings are now normalised to absence at the adapter boundary, with
whole-value matching so real names like "Unknown Fields Ltd" survive. The affected case
was not rerun: its outcome is unchanged, the field is dropped either way.

**What the evaluation actually shows:** Gemini's advantage over the rule extractor is in
what it refuses. It rejected the incidental mention, the sector-wide story, the analyst
scenarios and the broker rating by understanding what each article concerned. It also
extracted different counterparties for the two same-day Tata Motors events — Iveco and
Vertelo — which is what gives conservative linking something conflicting to separate on.

**Stated plainly:** the fixture is a designed test set of 21 hand-picked hard cases, not a
random sample. 100% on it means the known failure modes are covered, not that extraction
is solved. Live ingest produces ~160 articles per run against a 20-per-day budget, so most
production articles still take the rule fallback.

## 2026-09-05 — Gemini as the model-backed extractor

**What:** The model-backed extraction path runs. A Gemini adapter sits behind the
existing provider-isolated interface (D25), reading its credential from a gitignored
file through a loader that has no code path capable of printing it. Every result passes
schema validation, the deterministic grounding gate and subject resolution before
reaching the domain. The rule extractor remains the fallback and the evaluation
baseline, with separate provenance persisted per assessment.

**What the model actually did:** on the 11 fixture articles that completed before quota,
5 true positives, 5 correct rejections, 0 false positives. Gemini rejected an article
that only mentions the company inside someone else's contract — the hard case the rule
extractor passed by luck. It also proposed a `contract_value` the source did not contain,
and **grounding dropped it**, which is the gate doing on a real model exactly what it was
built for.

**Provider realities, recorded because they shaped the work:** Gemini 2.5 Flash is listed
but returns 404 to new keys, so the provider's named replacement is used. The free tier
allows 20 requests per model per day, which is why the evaluation is 11 calls rather than
21, and why the model is configurable — an evaluation run must not consume the production
model's budget.

**Fixes found while building:**

- Grounding rejected two-character values, so a correctly grounded `US` geography was
  dropped. The token floor was wrong, not the check: matching is token-level, so short
  tokens cannot match spuriously. Fabricated values are still rejected, and a test pins
  both halves.
- A truncated model reply parsed as garbage and was reported identically to a malformed
  one. Gemini 3.x spends output budget on reasoning, so the budget was raised and
  truncation is now a distinct, diagnosable failure.
- The page claimed "No ingest has run. Nothing here has been looked at yet" while
  displaying three assessments, because health was read from the disclosure source alone.
  Health now covers every source family that has run — a banner contradicting the content
  is exactly the misrepresentation this product exists to avoid.

**Rejected:**

- *Multi-provider orchestration.* D5 chose isolation, not a provider framework.
- *Weakening grounding to raise recall.* The short-token fix removed a false negative; it
  did not relax the guarantee.
- *Reporting metrics from a model other than the one that ran.* The extractor name carries
  provider, model and prompt version, so figures always name their source.

## 2026-09-05 — Step 2, news to meaningful change

**What:** Real news reaches the engine. A Google News adapter produces Evidence that
keeps publisher and subject company separate (D21); an extraction layer proposes
structure and a deterministic grounding gate decides what may enter the domain;
conservative event linking (D12) resolves LINK / CREATE_NEW / AMBIGUOUS from structured
attributes rather than headlines alone; corroboration counts independent publishers
rather than articles (D13); and the engine combines all of it with the market and
disclosure evidence already there.

**Why grounding is deterministic:** the anti-fabrication guarantee cannot depend on the
model cooperating. Any counterparty, product, geography, regulator or monetary figure
must appear in the source text or it is dropped and the drop recorded as a reason code.
During evaluation this caught an invented `contract_value` that a prompt instruction
alone would not have.

**Live results:** the Tata Motors/Iveco tender offer became one event with 8 evidence
records from 8 independent publishers. HDFC Bank coverage rendered as *4 articles · 3
independent sources* where a publisher repeated, and *4 articles · 1 independent source*
where one outlet posted four times — scored LOW, not HIGH. 14 HIGH out of 158 events.

**Corrections found while building:** two articles about one material event scored it
twice, because `MATERIAL_EVENT_TYPE` and `COMPANY_SPECIFIC_EVENT` both fired on the same
evidence — 58 of 157 assessments were HIGH before the fix, 11 after. The review gate then
found a silent evidence-loss bug: merging looked the link target up by scanning a recent
window, so an older event was not found and its id was reused for a fresh single-evidence
event, destroying the provenance and corroboration it had accumulated. Lookup is now by
primary key, and an unreadable target creates a duplicate rather than overwriting.

**Calibration from real data, not taste:** the link threshold was set by measuring real
multi-publisher coverage. Two outlets reporting one Consob approval scored 0.57 Jaccard;
two genuinely different same-day Tata Motors events scored 0.13. The threshold sits in
that gap.

**Known and stated:** no `ANTHROPIC_API_KEY` was available, so the Claude adapter has
only been exercised against stubbed transports. All extraction quality figures describe
the rule extractor: 86% recall at 100% precision on a 21-article fixture, 48%
classification across 167 live articles.

**Rejected:**

- *Embeddings for event identity.* D12 forbids them for the MVP, and a merge the system
  cannot explain is as bad as a ranking it cannot explain.
- *Counting articles as corroboration.* Syndication would manufacture confidence.
- *Trusting the model's own claim that it did not fabricate.* Prompting asks; the
  grounding gate verifies.
- *Blocking Step 2 on the missing API key.* The rule extractor is a real fallback, not a
  mock, so the system works now and improves when a key appears.

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
