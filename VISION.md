# Smart Market Watchlist — Product Vision

> **Thesis:** A watchlist should not tell you where your stocks are. It should tell you what changed while you were gone, what of that actually matters to *these* companies, and what deserves the next thirty seconds of your attention — and it should be able to show its reasoning.

---

## 1. Executive Vision

We are building an **attention system** for people who follow a set of companies.

A conventional watchlist is a rendering layer over a price feed. It answers *"where are my stocks now?"* — a question the user can answer at a glance and rarely needs answered. It leaves the harder question, *"what happened while I was gone, and does any of it matter?"*, entirely to the user.

That question is where the work is. Answering it today means opening each holding, scanning the day's move, checking whether the sector moved with it, searching for company news, discounting the news that is a rewrite of other news, remembering whether you already read it last week, and deciding whether any of it changes anything. That is a pipeline. The user runs it manually, badly, every time they open the app — and pays that cost on every visit, while the payoff is rare, because most days nothing meaningful happens.

The product we believe should exist runs that pipeline on the user's behalf and reports its conclusion, including the conclusion "nothing meaningful happened." It observes the information environment around each company, compares it against what this specific user had already seen, decides what is genuinely new and genuinely relevant, ranks it by how much attention it deserves, states how confident it is and why, and stops.

We do not own whether an event happened. Prices, filings, headlines, discussion volume — those come from external sources and always will. We own the layer above them: **is this event real, is it relevant to this company, is it new to this user, how significant is it, and can we defend surfacing it?**

**Scope for this version.** We are choosing Indian equities — NSE and BSE listings — as the primary watchlist universe. That is our decision about where to be useful first, not a constraint handed to us; nothing in the thinking below is specific to one market.

But the securities being *watched* and the evidence used to *understand* them are different things, and conflating them would be a scoping error. An Indian company's information environment routinely includes US technology market movement, European and Chinese markets, crude, lithium and semiconductor supply, USD/INR and other currency pairs, international competitors, overseas subsidiaries and foreign revenue exposure, and geopolitical developments nowhere near India. All of that is legitimate evidence when it bears on a company the user follows. It does not mean the system treats every global security as a first-class instrument a user can add to a watchlist — it does not, in this version.

**Indian equities as the watchlist universe; global information as contextual evidence where relevant.**

The system is judged not by how much it displays but by how much it correctly declines to display.

---

## 2. The Problem We Believe Actually Exists

The scarce resource is not market data. Market data is abundant, cheap, and largely commoditised. The scarce resource is the user's interpretive capacity.

A retail investor following 25 companies who checks in twice a week faces, on each visit:

- 25 price changes, of which perhaps 3 are outside their normal range and perhaps 1 is company-specific rather than sector-wide;
- some hundreds of headlines across those companies, most of which are syndication, aggregation, or restatement of a much smaller number of actual events;
- a set of developments in the wider environment — a commodity move, a currency move, a regulatory consultation, a competitor's launch — that matter enormously for two of the 25 and not at all for the other 23;
- no memory, anywhere in the product, of what they already read last Tuesday.

Existing products respond to this by adding surface area. More tabs, more feeds, more widgets, more notifications. Each addition is individually defensible and collectively makes the problem worse, because every one of them is another thing the user must check and dismiss.

Two structural failures follow:

**Interpretation is pushed onto the user.** The product shows a −3.1% move. Whether that move is alarming or unremarkable depends on the sector, the index, the international peer group, and whether anything specific to the company occurred — context the product has access to and chooses not to apply.

**The product has no memory of the user.** "Since you last checked" is implemented, when at all, as a price delta. But the user's actual question is about their *information* state, not the price at a timestamp. A user who read about a supplier strike on Monday does not need to be told about it again on Wednesday; they need to be told it ended.

The result is a product that is simultaneously noisy and lossy: it surfaces a great deal that does not matter, and it fails to surface things that do because they did not manifest as a large number.

---

## 3. Our Interpretation of "Smart"

"Smart" is not:

- **More data.** Adding social sentiment, macro feeds and competitor tracking as additional panels multiplies the user's work. A signal the user has to check is not intelligence; it is another chore.
- **AI summaries.** Summarising everything relocates the overload rather than removing it. Twenty-five two-sentence summaries is still twenty-five things to read, now with a layer of paraphrase between the user and the source. Summarisation is a presentation technique applied *after* the decision of what to show; it is not the decision.
- **Prediction.** We are not forecasting prices. A product that claims to know what happens next is making a claim it cannot support, and one bad call destroys the trust the rest of the product depends on.

"Smart" for this product means one thing: **the system decides what not to show you, and can defend the decision.**

Suppression is the feature. A product that confidently reports "nothing meaningful changed across 22 of your 25 companies" has done more work than one that renders 25 rows, and the user has to trust it more. That trust is earned by explainability, not asserted by branding — which is why the ability to answer *"why am I seeing this?"* is a load-bearing part of the product rather than a nice detail.

The corollary: **an unexplainable correct answer is worth less to us than an explainable one.** If we cannot say why something was ranked HIGH, we should not rank it HIGH.

---

## 4. The Core Product Experience

Returning to the product should feel like being briefed by someone competent who has been paying attention on your behalf and respects your time. Short, specific, honest about what they don't know, and finished quickly.

The user opens the app. The first thing on screen is not a table of tickers. It is a verdict:

> **3 things deserve your attention.** Since your last visit — Monday, 10:42.

**RELIANCE — ATTENTION: HIGH · CONFIDENCE: MEDIUM**

Price: +0.7% since you last checked. That is within its normal range and is not why this is here.

What changed:
- A major competitor announced a large capacity expansion in an overlapping segment (2 independent credible sources; not company-confirmed).
- A commodity this company has significant exposure to moved sharply.
- Discussion volume around an approaching regulatory decision rose well above its usual level.

Why it is ranked highly: three independent, company-relevant developments since your last visit, none of which is reflected in the price yet. *We are not claiming the price should have moved — only that the information around this company has changed materially and the price alone would not have told you.*

**INFOSYS — ATTENTION: LOW · CONFIDENCE: HIGH**

Price: −3.1%. Context: the IT sector fell approximately 2.8% and the relevant international technology index declined similarly. No company-specific development detected.

The move is broadly consistent with sector-wide behaviour. This is context, not a causal explanation — we have not established that the sector move *caused* this one.

**TATA MOTORS — PREVIOUSLY FLAGGED, NOW RESOLVED**

The supplier strike we flagged on Monday has ended following an agreement. Production is expected to resume. This is no longer an active concern and will stop appearing.

**11 other companies — no meaningful change detected** since your last visit. *(Expand to see them.)*

**1 company — unable to fully evaluate.** Our primary news source for HDFC Bank has been unavailable since 06:40 today. Price data is current; event coverage is not. We are not claiming nothing happened.

That last block matters as much as the first. A silent watchlist and a blind watchlist look identical unless the product is honest about the difference.

Everything above is reachable in one screen and readable in under a minute. The detail — the sources, the timestamps, the full scoring rationale, the 11 quiet companies — is available on demand and hidden by default.

---

## 5. The Meaningful Change Thesis

**Magnitude is not meaningfulness.**

A large price movement is not automatically significant. A stock falls 3%; its sector fell 2.8%; the relevant international market fell similarly; nothing company-specific is detectable. The most useful thing the product can say is that this looks like the market moving, not the company — and that it deserves *less* attention than the number suggests.

A negligible price movement does not mean nothing happened. A stock moves +0.5% while a major competitor launches a directly competing product, a key supplier halts, discussion volume triples, and a regulatory decision approaches. The information environment around that company has changed substantially. Price is one signal among many, and often the slowest.

**Working definition.** A *meaningful change* is a change in the information environment around a company that (a) is unusual relative to that company's own baseline, (b) is plausibly relevant to that specific company, (c) is material enough to alter what a reasonable follower of the company would want to know, and (d) is new to *this* user given what they had already seen.

All four tests must pass. Dropping (a) produces a product that reports routine activity as news. Dropping (b) produces a product that attaches every geopolitical headline to every stock. Dropping (c) produces a product that reports true but trivial facts. Dropping (d) produces a product that repeats itself, which is the fastest way to teach users to ignore it.

Note what this definition does *not* require: a price move. An event with no price reaction can be highly meaningful, and a large price move with no identifiable cause is itself a finding worth reporting honestly — *"this moved unusually and we cannot yet explain it"* is a legitimate output, and a more honest one than inventing a reason.

---

## 6. Attention, Not Recommendations

The system's output vocabulary is **HIGH / MEDIUM / LOW / NO MEANINGFUL CHANGE**, plus **UNABLE TO EVALUATE**. It is deliberately not BUY / SELL / HOLD.

This is not timidity. It is a claim about what we can actually defend.

We can defend, from evidence, statements of the form: *"this is unusual for this company, it is relevant to this company for these reasons, two independent credible sources report it, and you had not seen it."* Every clause there is checkable.

We cannot defend *"you should buy this."* That requires knowing the user's holdings, horizon, risk tolerance, tax position and alternatives — none of which we have — plus a view on future prices, which we do not have and do not intend to develop. A product that says it anyway is bluffing.

There is also an asymmetry in the cost of being wrong. A wrongly-ranked HIGH costs the user twenty seconds and a little trust; the failure is visible, bounded and recoverable. A wrong recommendation costs them money and is not recoverable by better ranking later. We choose the output space where our errors are survivable.

And there is a regulatory reality: personalised investment advice is a licensed activity. Ranking what deserves investigation is not. We intend to stay clearly on one side of that line, in both behaviour and language.

The product's job ends at *"this is worth your attention, and here is why."* What the user does next is theirs.

---

## 7. Information State & "Since You Last Checked"

Most products interpret "since you last checked" as arithmetic on a price series. We interpret it as a diff between two **information states**.

The system conceptually maintains, per user, a checkpoint: what the system knew about each of their companies at the moment they last looked, and what of that was actually presented to them. On return, the question is not "how has the price changed" but "what does the system know now that this user had not already been shown."

Consequences we accept deliberately:

- **Two users following the same stock can get different answers.** A user who last checked an hour ago and one who last checked in March should not see the same page. This is correct behaviour, and it means the evaluation cannot be a single global computation cached per ticker and served to everyone.
- **Time-since-visit changes the shape of the answer, not just its length.** After thirty seconds, the honest answer is usually "nothing new." After three days, it is a set of events. After six months, an event-by-event replay would be absurd; the useful answer is a narrative of what changed structurally and what is still live — most individual events from month two are no longer worth a line.
- **Resolved items must retire.** If we flagged a concern and it has since resolved, the user's outstanding question is about the resolution, not the original flag. Without this, flags accumulate permanently and the product becomes a graveyard of stale warnings.

**What "seen" means.** This needs a stated position, because the whole notion of a checkpoint rests on it. Ours: *information must not become old merely because it was technically delivered.*

Opening the dashboard does not mean every surfaced event has been seen, and rendering an event to the screen is not acknowledgement of it. The system instead maintains a checkpoint representing the user's previous **meaningful review session**. Events occurring after that checkpoint are the candidates for "since you last checked," and the checkpoint advances only once the user has had a genuine opportunity to review the summary — not the instant the page loads. Explicit per-event read state is not required for the core version, and would only earn its place if it turned out to be cheap.

This deliberately avoids two bad extremes. **Page-opened-equals-acknowledged** destroys information on an accidental open, a refresh, or a tab restored by the browser — the user loses the briefing they never read, which is the worst failure this product can have. **Perfect per-event acknowledgement** is more faithful but imposes interaction and state complexity on the user and the system that the core experience does not yet justify (§18). The exact UX trigger for advancing the checkpoint is a design decision, deliberately left open; the semantic requirement above is not.

This also forces a separation we expect to matter architecturally. **Event state** — what is happening in the world, and where each development sits in its lifecycle (§11) — is a property of the world, shared across every user following that company. **User state** — what this particular person has already had an opportunity to understand — is a property of one person. They evolve on different clocks and for different reasons, and collapsing them into a single "is this new?" flag would make both wrong. They should stay separate concepts downstream.

---

## 8. Company Context & Relevance

Events do not have universal significance. A semiconductor supply disruption is a first-order event for an automaker and close to noise for a bank. A crude oil move is good for a producer, bad for an airline, and complicated for a chemicals company. Attaching the same headline to every company is the single most common way a product like this becomes noise.

So relevance has to be decided per company, which means the system needs a lightweight, evolving notion of **what each company is exposed to**: its sector and industry, the geographies that matter to it, its main products and business units, its notable competitors, the suppliers and inputs it depends on where those are known, the commodities and currencies it is sensitive to, its regulatory exposure, and its index memberships.

Two honest constraints:

**Our knowledge will be partial.** We will not have a complete supply-chain map for every listed company, and any product that claims to is overstating. Company context must therefore be able to represent uncertainty and absence — "we do not know this company's supplier exposure" is a valid state, and it should make the system *more* conservative about relevance claims, not less.

**There is a real trade-off between accuracy and coverage.** Hand-curated context is accurate and does not scale. Inferred context scales and is sometimes wrong. We expect to use both, and to attach confidence to the context itself, so that a relevance judgement built on an inferred supplier relationship is visibly weaker than one built on a stated business segment. Relevance confidence and evidence confidence are separate things, and both belong in the final answer.

Company context is a means to an end. It exists to let the system say *"this matters to this company because…"* — not to become a knowledge-graph project in its own right. See §18.

---

## 9. Signal Universe

The following are **evidence classes the system reasons over**, not tabs, panels or features. If the user has to open sixteen sections to find out what happened, we have rebuilt the problem with better data.

**Company behaviour in the market** — price movement, volume, volatility, movement that is unusual relative to the company's own baseline and relative to its peers and index. Establishes *that* something happened, rarely *what*.

**Company disclosure and corporate action** — earnings and guidance, exchange filings, management and leadership change, dividends, buybacks, splits, bonus and rights issues, mergers, acquisitions, spin-offs, promoter and insider transactions, block and bulk deals, ownership changes. The most reliable class: authoritative, timestamped, and specific to the company by construction.

**Company ecosystem** — competitors (launches, pricing, earnings, acquisitions, partnerships, market-share developments), suppliers and supply chain (disruption, strikes, shortages, logistics and port problems, manufacturing halts), customers and major contract or partnership wins, and the commodities the company consumes or produces. Relevance here depends entirely on company context (§8).

**Operating environment** — macroeconomic conditions and rates, inflation, currencies, geopolitical developments (sanctions, tariffs, trade restrictions, conflict, elections, regional instability), regulatory and legal developments (regulator actions, policy, approvals, investigations, litigation, sector rules), index and structural events (inclusion, removal, rebalancing), and international markets, sector indices and foreign peers. Almost always relevant to *someone* and almost never relevant to *everyone*; surfaced only where a defensible connection to the company exists. For an Indian-equity watchlist most of this class is, by construction, non-Indian information — which is exactly the distinction drawn in §1: global evidence, domestic universe.

**Crowd signals** — public discussion volume, emerging narratives, shifts in attention and sentiment on public forums. Treated as a signal that *people are talking*, never as evidence that a claim is true. Useful primarily as an early indicator and as corroboration-of-interest, never as corroboration-of-fact.

**Forward-looking catalysts** — scheduled earnings, index rebalances, regulatory decision dates, shareholder votes, planned launches, policy meetings. The product should not only look backward; *"nothing has happened yet, but something relevant is approaching"* is often the most actionable thing we can say.

**On availability.** These families differ enormously in accessibility, licensing cost, latency and reliability, and we are not assuming we will have all of them. The system must produce a correct, honest answer from whatever subset is actually available, and must say which classes it could not evaluate rather than quietly reporting a partial view as a complete one (§14). A version of this product using only market data, disclosures and news is still the product; a version that requires all sixteen families to function is not a product at all.

---

## 10. From Signal to Meaning

A conceptual model of how raw evidence becomes an attention decision. It is not an architecture, and the stages need not map one-to-one onto components.

**Raw signals** — heterogeneous inputs from external sources. We own none of these; we own our handling of them.

**Normalization** — express heterogeneous inputs as a common notion of an event: what, which entities, when, from where, with what stated certainty. The point is to make things comparable, not to make them true.

**Deduplication** — fifteen articles about one announcement are one event with fifteen mentions, not fifteen events. Getting this wrong makes the system's significance scoring self-reinforcing: repetition would masquerade as importance, which is exactly the failure mode of every news aggregator.

**Company relevance** — does this event plausibly bear on this company, and why? Answered against company context (§8), producing a stated reason, or a decision not to attach the event at all.

**Corroboration and source assessment** — where did this originate, how reliable is that origin, and do genuinely independent sources support it? Note that ten outlets syndicating one wire report is one source, not ten; independence has to be assessed, not counted.

**Significance** — is this unusual for this company, is it material, is it company-specific or environmental, has its status changed, does it alter what we understand about the company?

**User information state** — has this user already been shown this? (§7)

**Attention ranking** — the surviving events are ordered into HIGH / MEDIUM / LOW / NO MEANINGFUL CHANGE for this user at this moment.

**Explanation** — the record of what changed, why it matters, why it ranked where it did, how confident we are, and how fresh the underlying data is.

Two properties of this model matter more than its stages. First, **it is subtractive**: each stage's job is to discard, downgrade or defer, and by the end most candidate events should be gone. Second, **the explanation is a by-product of the decision, not a narration added afterwards** — the reasons are the same reasons the ranking used. A pipeline that decides first and explains second can produce plausible explanations for wrong decisions, which is worse than no explanation.

---

## 11. Event Lifecycle

Events are not points; they are things with a state that changes. The system tracks, conceptually:

| State | Meaning |
|---|---|
| **NEW** | First credible detection. |
| **DEVELOPING** | Real, ongoing, outcome not yet determined. |
| **CONFIRMED** | Corroborated by authoritative evidence — a filing, a company statement, an official decision. |
| **ESCALATING** | Growing in scope, severity or corroboration since first detection. |
| **WEAKENING** | Losing corroboration, scope or relevance. |
| **CONTRADICTED** | Credible evidence now disputes the original report. |
| **RESOLVED** | The situation has concluded; it is no longer an active concern. |
| **STALE** | No further evidence for long enough that we no longer treat it as live, without knowing how it ended. |

Most products are competent at NEW and nothing else. The states that make the product feel intelligent are **RESOLVED** and **CONTRADICTED**: being told that the thing you were worried about is over, or that the report you saw on Monday has been disputed, is more valuable than being told about a fresh unrelated item — and no product does it.

It is also what keeps the surface small. Without lifecycle tracking, flags only accumulate. The system becomes a list of everything that ever looked concerning, which the user learns to skip.

**We should be honest that resolution is harder to detect than onset.** Onsets are reported enthusiastically; resolutions are reported quietly or not at all. Strikes end in a paragraph on page nine. This means STALE will be a common terminal state, and the product must distinguish *"this concluded"* from *"we stopped hearing about it"* rather than dressing the second up as the first. Time-based decay is a reasonable fallback for the second case; presenting decay as resolution would be a lie.

---

## 12. Trust, Confidence & Provenance

Financial information arrives from sources with radically different epistemic weight, and a product that flattens them is misleading regardless of how accurate its individual facts are. An exchange filing and an anonymous forum post must never render identically.

We distinguish, roughly in descending order of weight: **verified fact** (computed by us from primary data — a price change, a volume ratio), **official disclosure** (exchange filing, regulatory decision, company statement), **credible reporting** (established outlets, attributed), **corroborated reporting** (multiple genuinely independent credible sources), **social discussion** (real as a signal of attention, not as evidence of fact), **speculation**, and **system inference** (our own conclusion, which must be labelled as ours and never laundered into apparent fact).

Confidence is reported **separately from attention**, because they are different questions. "Something significant may have happened, we are not sure" and "something modest happened, we are certain" are both legitimate, and collapsing them into one number destroys information the user needs:

- **HIGH** — confirmed by disclosure or primary data, or corroborated by multiple independent credible sources.
- **MEDIUM** — reported by credible sources, not officially confirmed.
- **LOW** — early, single-source, or driven mainly by social discussion; no authoritative confirmation.

Two rules we hold to. **Corroboration requires independence** — syndicated copies of one report add volume, not evidence. And **confidence is allowed to fall**: an item that was MEDIUM on Monday can be LOW on Wednesday if the corroboration did not arrive, and the product should be willing to say so.

---

## 13. Causation vs Context

The system must not manufacture causal claims from co-occurrence. "The stock fell because of X" is a strong claim, and temporal proximity does not establish it. Markets produce coincidences constantly; a product that narrates every one of them as a cause is confidently wrong at scale, and users cannot tell which of its explanations are the sound ones.

We use a deliberate ladder of language, and the system's default voice is the descriptive end of it:

- **Observation** — *"Declined 3.2%."* Computed, not interpreted.
- **Context** — *"The sector declined approximately 2.8% over the same period."* True, adjacent, no causal claim.
- **Possible relevance** — *"A regulatory announcement affecting this industry occurred today."* Flagged as potentially connected, explicitly not asserted as the cause.
- **Established causation** — reserved for cases where evidence explicitly supports it: the company attributed it, the filing states it, the event is definitionally causal (a scheduled corporate action).

In practice this means preferring *"consistent with"*, *"coincided with"*, *"may relate to"* over *"because of"*, *"driven by"*, *"caused by"* — and treating unexplained movement as an honest finding rather than a gap to be filled. This is a hard constraint on generated text as much as on ranking logic: language that overstates certainty is a correctness bug, not a style preference.

---

## 14. Data Freshness & Failure Philosophy

Every input we depend on will, at some point, be delayed, partial, stale, contradictory or absent. This is normal operating condition, not an exceptional case, and how the product behaves under it is a large part of whether it can be trusted at all.

**The central distinction:**

> **"No meaningful change detected"** is a conclusion. It says we looked, across the sources we expect to have, and found nothing that met the bar.
>
> **"Unable to fully evaluate"** is an admission. It says one or more sources we depend on were unavailable, and our silence is not evidence of quiet.

Conflating these is the most damaging thing this product could do, because the entire value proposition rests on the user being able to trust silence. If "nothing here" might secretly mean "we couldn't see," then the user has to check everything manually anyway, and we have built nothing.

From this, several commitments follow:

- **Coverage is part of the answer.** Every verdict carries what it was based on and what was missing. Partial coverage is reported as partial.
- **Freshness is visible per source, not per page.** Prices can be two minutes old while news coverage is six hours stale. A single "updated just now" over the whole screen would be false.
- **Market state is explicit.** Closed, pre-open, post-close, holiday, and the fact that a user's companies may span sessions in different time zones — these change what the numbers mean, and the product should say which regime it is reporting.
- **Cached data is labelled as cached.** Serving stale values as current is never acceptable, even when it looks better.
- **Conflicting reports stay conflicting.** When credible sources disagree, we show the disagreement rather than silently picking one. Disagreement among sources is itself information.
- **Corrections propagate.** A story corrected after publication must be able to change an already-surfaced item's state (§11), including retracting it.
- **Degrade, don't fail.** With market data but no news, the product still reports movement honestly and says event coverage is unavailable. Partial function with stated limits beats an error page, and beats a confident-looking page built on half the inputs.

---

## 15. Explainability

Every attention decision should be answerable to the question *"why am I seeing this?"* — with the actual reasons, not a plausible-sounding reconstruction.

The user-facing form is a short ledger of what pushed the item up and what pushed it down:

```
Why you're seeing this:
  + Company-specific event, corroborated by two independent credible sources
  + Discussion volume well above this company's normal range
  + A commodity this company is materially exposed to moved significantly
  + Occurred after your previous visit
  − Price movement itself is within normal range
  − No official company confirmation yet

ATTENTION: HIGH        CONFIDENCE: MEDIUM
```

Three things make this real rather than decorative:

**Negative contributions are shown.** Listing what argued *against* surfacing something is what distinguishes an explanation from a justification, and it is what lets a user calibrate the system rather than just obey it.

**The explanation is the decision record.** The factors shown are the factors used. This constrains how we build the ranking — a system whose reasons cannot be enumerated cannot produce this display, which is a design constraint we accept in exchange for a product a user can audit and a judge can inspect.

**Language generation is downstream of it.** A model may render these factors into a readable sentence. It may not add a factor, drop one, or upgrade the certainty of the wording. The facts, the numbers, the timestamps, the provenance and the ranking are established before any text is generated, and the text is a rendering of them.

---

## 16. Product Principles

1. **Magnitude is not meaningfulness.** The size of a number is not the importance of an event.
2. **Relevance is company-specific.** The same event means different things to different companies; some it does not concern at all.
3. **Compare information states, not just prices.** "Since you last checked" is a diff over what the user knew, not over a price series.
4. **Attention is scarce.** Success is minimising what the user must read while preserving what they must know.
5. **Uncertainty must be visible.** Source quality, corroboration and confidence are part of the answer, never smoothed away.
6. **Intelligence must be explainable.** If we cannot say why, we do not rank it highly.
7. **Information has a lifecycle.** Things escalate, weaken, resolve and go stale, and we track that; resolution is as valuable as detection.
8. **Context is not causation.** We report what co-occurred; we assert cause only with evidence.
9. **Silence can be useful — but only if it is honest.** "Nothing meaningful changed" is a real feature and must never be indistinguishable from "we could not look."
10. **Complexity must earn its place.** Every mechanism must trace to a wrong answer it prevents.

---

## 17. What We Deliberately Do NOT Build

- **An automated financial adviser.** No personalised advice, no allocation, no position sizing. (§6)
- **A buy/sell/hold or price-prediction engine.** We do not forecast prices and will not imply that we do.
- **A trading bot.** No execution, no order placement, no broker integration in scope. Users curate their own watchlists.
- **A generic news aggregator.** We do not want completeness of coverage; we want the small subset that survives relevance and significance.
- **A social sentiment dashboard.** Crowd signals are input to a judgement, never a product surface of their own, and never treated as truth.
- **A global multi-market watchlist.** Users watch Indian listings in this version. Global markets, commodities and currencies inform the analysis; they are not instruments the user adds. (§1)
- **A Bloomberg terminal.** We are not competing on breadth of data or professional-grade tooling. Our user has a day job.
- **A wall of widgets.** Sixteen signal families do not become sixteen panels. The synthesis is the product; exposing the raw inputs as UI would be an admission that we failed to synthesise. (§9)
- **An LLM wrapper.** A model that reads everything and decides what is important is not this product. Objective facts, calculations, provenance, state and freshness are established deterministically; language models assist with extraction, classification and phrasing within those bounds. (§15)
- **A complete model of the world economy.** We will not have every supply chain or every exposure. The system expresses partial knowledge rather than pretending to completeness. (§8)
- **A notification stream.** The product is deliberately pull-based. Alerts and digests are plausible later extensions; adding another interrupting channel to a product about protecting attention would contradict the premise. Natural-language querying is likewise a possible extension, and explicitly not the core — the intelligence must exist in the evaluation, not in a chat box.

---

## 18. Simplicity vs Necessary Complexity

The test we apply: **complexity is justified when it is the cheapest way to prevent a wrong answer the user would notice.** Complexity that only makes the system look sophisticated is a defect.

**Justified — each of these prevents a specific, visible failure:**

| Mechanism | The wrong answer it prevents |
|---|---|
| Per-user information state | Repeating things the user already read; treating a 30-second absence like a 3-day one |
| Event normalization | Being unable to compare a filing with a headline with a price move |
| Deduplication | Fifteen copies of one story registering as fifteen independent confirmations |
| Company relevance via context | Attaching every macro headline to every company |
| Source provenance and corroboration | A forum rumour and an exchange filing looking equally credible |
| Freshness and coverage tracking | Reporting silence when we were actually blind |
| Significance evaluation and attention ranking | A product that shows everything, i.e. the original problem |
| Confidence modelling | Presenting uncertain information as settled |
| Event lifecycle | Permanent accumulation of stale, already-resolved warnings |
| Graceful degradation | Total failure when one dependency is down |

**Over-engineering, for a project at this stage:**

- Microservices adopted for appearance rather than for a boundary that actually exists.
- Streaming infrastructure with no demonstrated throughput need.
- Trained ML models where transparent, tunable rules would perform comparably and be explainable — and explainability is a product requirement, so an opaque model that scores slightly better is still the worse choice here (§15).
- Real-time processing where near-real-time is indistinguishable to a user who visits twice a week. The product is pull-based; latency budgets should be set by that.
- A large knowledge graph, when the product needs a bounded set of exposures per company.
- Integrating a dozen data providers before the evaluation logic is right. A correct answer over three sources beats a confused answer over twelve.
- Distributed infrastructure ahead of the scale that requires it.
- Price prediction of any kind — out of scope by principle, not by capacity.
- Elaborate personalisation and learning-from-feedback before the base meaningful-change evaluation is trustworthy.

**Stated trade-off:** favouring transparent rules over learned models costs us some accuracy at the margin and will require manual tuning of thresholds. We accept that, because a system that cannot explain itself cannot deliver §15, and §15 is the product.

**On scale:** the design should not *preclude* larger watchlists and more users — per-user evaluation over shared per-company analysis is the obvious shape, and most of the expensive work (ingestion, normalization, dedup, relevance) is per-company and shared, while the cheap work (user-state diffing, ranking) is per-user. Recognising that boundary now costs nothing. Building the distributed system it eventually implies, before there are users, costs everything.

---

## 19. Conceptual System Responsibilities

Responsibilities the eventual system must fulfil. No technology choices are made here; those belong in an architecture document.

**Ingestion** — acquire evidence from external sources, tolerate their outages and rate limits, record what was fetched and when, and record what could *not* be fetched. Coverage gaps are data, not silent failures.

**Normalization and identity** — convert heterogeneous inputs into a comparable event representation, and determine when two reports describe the same underlying occurrence. Stable event identity is what makes deduplication, lifecycle and "already seen" possible at all.

**Company context** — maintain each company's exposures and relationships, with confidence and explicit gaps, and keep it current through renames, ticker changes and corporate actions.

**Evaluation** — relevance, corroboration, significance and attention ranking, producing both a decision and the enumerated reasons for it.

**User state** — per-user checkpoints of what was known and what was shown, durable across sessions and devices, correct when the same user has two sessions open.

**Presentation** — render the verdict, its reasons, its confidence and its freshness, with the detail available but subordinate. Language generation lives here, bounded by facts established upstream.

**Observability** — the ability to answer, after the fact, why a specific item was surfaced or suppressed for a specific user at a specific time. This is a correctness tool as much as an operations one; without it, ranking regressions are undetectable.

The separation that protects correctness: **source of truth → interpretation → presentation.** The market source says the price changed from X to Y. The news source says a contract was announced. The evaluation says these collectively deserve attention and why. The presentation layer explains it clearly in two sentences. Facts do not originate in the presentation layer, and interpretation does not overwrite the record of what was observed.

---

## 20. Edge Cases We Consider Fundamental

These are product-defining, not exotic. How the system behaves here is most of what separates a demo from something usable.

**Coverage and source failure**
- *A source is unavailable.* Report the gap explicitly; never let a coverage failure render as a quiet watchlist. (§14)
- *Partial responses / some companies covered, others not.* Coverage is stated per company, not per page.
- *Events occurred while ingestion was down.* On recovery, backfill and reconcile — late-arriving events are still new *to the user*, even if old in wall-clock terms.

**Evidence quality**
- *Duplicate reports of one event.* Collapse to one event with multiple mentions; do not let repetition inflate significance.
- *Conflicting reports.* Show the conflict and the sources; do not silently pick a winner.
- *A single major source disagrees with several others.* Neither auto-defer to the majority nor to the loudest; surface as disputed and let confidence reflect it.
- *An event is corrected after publication.* Correction propagates to the already-surfaced item and can retract it.
- *A social rumour goes viral.* Rising discussion is a real signal about attention, reportable as such at LOW confidence with no assertion of truth; virality never promotes an unverified claim to fact.

**Timing and market state**
- *Market closed, pre-open, post-close, holiday.* State the regime; a flat price at 3am is not information.
- *Companies across time zones.* "Today" is ambiguous across sessions; report against explicit session boundaries.
- *Delayed feeds.* Label delay rather than implying live data.

**User state**
- *User returns after 30 seconds.* The correct answer is almost always "nothing new," delivered instantly. This case must feel light, not like a re-run.
- *User opens the page and closes it immediately, or the tab reloads.* The checkpoint must not have advanced. An unread briefing that disappears because the page technically rendered is the failure mode §7 exists to prevent.
- *User returns after six months.* Not a six-month event replay — a structural summary of what changed and what is still live.
- *A stock is newly added.* There is no prior checkpoint; we must establish a baseline honestly rather than dumping history as if it were new. Some initial context is useful; a flood is not.
- *A stock is removed and re-added.* Decide whether prior information state survives — we lean toward preserving it, since the user's knowledge did not disappear when they removed the row.
- *The same user in two sessions at once.* Checkpoint updates must not race into an inconsistent "last seen."

**Company identity**
- *Renames, ticker changes, mergers, demergers, spin-offs.* The company the user is following persists across its identifiers; history must not be orphaned by a symbol change.
- *Corporate actions distorting price series.* Splits, bonuses and dividends produce price changes that are not movements; treating them as unusual behaviour would be a straightforward correctness failure.

**Signal-price mismatch** — the cases that define the product
- *Price moved with no detected company event.* Report the move with sector and peer context, and say plainly that no company-specific cause was found. Do not manufacture one. (§13)
- *A relevant event occurred with no price movement.* Surface it — this is precisely the case a price-based watchlist misses. (§5)
- *Price moves before the explanation is available.* Report as developing; expect the explanation to arrive later and update the item rather than leaving a permanent unexplained record.

---

## 21. How This Vision Addresses the Judging Criteria

**Engineering depth.** The hard problems here are not glamorous ones. Stable event identity across heterogeneous sources; deduplication that distinguishes independent corroboration from syndication; per-user information state that stays correct across devices, concurrent sessions and long absences; a lifecycle model with honest resolution and decay; a separation between per-company shared analysis and per-user evaluation that makes larger watchlists tractable without distributed infrastructure. These are real correctness problems with observable failure modes, chosen because the product breaks without them — not because they are impressive.

**Product and problem interpretation.** The brief says "meaningfully changed." Our answer is a specific and defensible position: meaningfulness is not magnitude, relevance is company-specific, and "since you last checked" is a diff over information state rather than price. The decision to make suppression and honest silence first-class outputs — including "nothing meaningful changed" and "unable to fully evaluate" as distinct results — follows from taking the brief's word "meaningfully" seriously rather than treating it as decoration on a price table.

**Edge cases and resilience.** §20 is derived from the product thesis, not appended to it. Because the value proposition rests on trusting silence, coverage gaps, stale data, conflicting sources, corrections, dedup, corporate actions and concurrent user state stop being defensive extras and become correctness requirements. The "no meaningful change" vs "unable to evaluate" distinction is the clearest single expression of that.

**Code quality and simplicity.** §18 states the test — complexity must trace to a wrong answer it prevents — and applies it in both directions, including an explicit list of things we are choosing not to build and a stated cost for choosing transparent rules over learned models. The three-layer separation (source of truth / interpretation / presentation) is a maintainability decision as much as a correctness one: it keeps generated language from becoming a place where facts originate.

**Originality and thoughtfulness.** The independent choices are the ones we can defend: attention levels instead of buy/sell/hold; lifecycle tracking so resolutions retire and stale warnings do not accumulate; explanation as the decision record rather than a generated narration; deliberately pull-based rather than notification-driven, because adding an interrupt stream to an attention product would contradict its premise; and an explicit refusal to let a language model be the source of truth. Each is a position we would defend against the obvious alternative.

---

## 22. Product North Star

> **If the user gives us only thirty seconds after returning to their watchlist, can we correctly decide what deserves those thirty seconds?**

Every later decision — product, design, architecture — should be checked against this question, because it forces the trade-off rather than hiding it.

It rules out adding a feature because it is interesting: a new panel costs seconds the user does not have, and must displace something. It rules out surfacing a signal we cannot explain, because an unexplained item consumes attention it cannot justify. It rules out silent failure, because thirty seconds spent on a page that was blind is thirty seconds worse than wasted. And it rules out both directions of error symmetrically — showing what does not matter and hiding what does are equally failures of the same question.

It also sets the bar for success honestly. Not *"we displayed a lot of market information."* Rather:

**A returning user understands the most important changes affecting their companies in seconds, understands why each was surfaced, can see how confident we are and what we could not see — and can confidently ignore everything else.**

That last clause is the one that is hard to earn and easy to lose.
