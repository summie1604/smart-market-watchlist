"""Real articles, captured 2026-09-05, with the properties extraction must get right.

Deliberately weighted toward the hard cases: several companies in one headline, a
sector-wide story, an incidental mention, syndicated coverage, two same-day events,
speculation, and a headline whose meaning only appears in the body.

These assert *semantic invariants*, never natural-language equality. The point is not
that an extractor produces particular words — it is that it names the right company,
invents no counterparty, and does not turn a market summary into a company event.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ARTICLES", "Article"]


@dataclass(frozen=True)
class Article:
    label: str
    publisher: str
    symbol: str
    company: str
    title: str
    body: str = ""

    # Expectations. ``None`` means "no expectation", not "must be absent".
    should_classify: bool = True
    """Whether a competent extractor should produce an event at all."""
    concerns_subject: bool = True
    """Whether the article is genuinely about the subject company."""
    must_not_invent: tuple[str, ...] = ()
    """Values an extractor must never emit, because the source does not support them."""


ARTICLES: tuple[Article, ...] = (
    # --- straightforward company-specific events ---
    Article(
        label="clear-partnership",
        publisher="News On AIR",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="US President Trump Announces $300 Billion Partnership with Reliance to Build First Major US Refinery",
    ),
    Article(
        label="clear-acquisition",
        publisher="The Economic Times",
        symbol="TMCV",
        company="Tata Motors",
        title="Tata Motors' Iveco takeover offer gets Consob nod; acceptance period opens Sep 7",
    ),
    Article(
        label="leadership-change",
        publisher="Bloomberg.com",
        symbol="HDFCBANK",
        company="HDFC Bank",
        title="CEO's Refusal to Overhaul Bank Fueled Surprise HDFC Shakeup",
    ),
    Article(
        label="product-launch",
        publisher="BW Marketing World",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance Consumer Products Forays Into Ice Cream Market With 'Bombay Creamery'",
    ),
    Article(
        label="fundraise-ipo",
        publisher="The Economic Times",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Jio sets eyes on Navratri-Diwali period to launch mega $4 billion IPO",
    ),
    Article(
        label="stake-sale",
        publisher="scanx.trade",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="JMFARC, RIL reduce Alok Industries stake to 71.93% via open market sales",
    ),
    # --- must NOT become company events ---
    Article(
        label="market-summary",
        publisher="IndiaIPO",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Sensex Today | Stock Market Live: Sensex jumps 660 pts, Nifty nears 24,000; Reliance up",
        should_classify=False,
        concerns_subject=False,
    ),
    Article(
        label="stocks-to-watch-list",
        publisher="Livemint",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Stocks to watch today: Reason why these shares are in focus for Wednesday's trade",
        should_classify=False,
        concerns_subject=False,
    ),
    Article(
        label="price-move-only",
        publisher="MarketWatch",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance Industries climbs Friday, outperforms competitors",
        should_classify=False,
    ),
    Article(
        label="broker-rating",
        publisher="MarketsMojo",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance Industries Ltd is Rated Sell",
        should_classify=False,
    ),
    Article(
        label="incidental-mention",
        publisher="scanx.trade",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Konstelec Engineers receives amended Rs 9.19 crore order from Reliance Industries",
        concerns_subject=False,
        must_not_invent=("Konstelec wins contract from Tata",),
    ),
    Article(
        label="sector-wide",
        publisher="Upstox",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Kwality Wall's, Vadilal Industries: Why ice cream stocks fell over 3.6% after Reliance entry",
        concerns_subject=False,
    ),
    # --- speculation and rumour ---
    Article(
        label="speculative-ipo",
        publisher="Bhaskar English",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance may launch Jio IPO during Navratri or Diwali: Mukesh Ambani will bring it",
    ),
    Article(
        label="analyst-scenarios",
        publisher="CNBC TV18",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Three upside scenarios that JPMorgan lists out for Reliance Industries going forward",
        should_classify=False,
    ),
    # --- syndication: one story, several outlets ---
    Article(
        label="syndicated-icecream-1",
        publisher="Livemint",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="After shaking up cola market, Mukesh Ambani's Reliance brings Rs 10 ice cream",
    ),
    Article(
        label="syndicated-icecream-2",
        publisher="Tehelka",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance launches Bombay Creamery ice cream, prices start at Rs 10",
    ),
    Article(
        label="syndicated-icecream-3",
        publisher="opindia.com",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="Reliance enters India's Ice Cream market with Bombay Creamery, begins western rollout",
    ),
    # --- two genuinely different same-day events for one company ---
    Article(
        label="same-day-a-iveco",
        publisher="Moneycontrol.com",
        symbol="TMCV",
        company="Tata Motors",
        title="Tata Motors Iveco takeover offer clears Consob review, acceptance opens September 7",
    ),
    Article(
        label="same-day-b-different",
        publisher="The Economic Times",
        symbol="TMCV",
        company="Tata Motors",
        title="Tata Motors signs supply agreement with Vertelo for 500 electric buses in Karnataka",
    ),
    # --- vague headline, body carries the meaning ---
    Article(
        label="vague-headline-with-body",
        publisher="Business Standard",
        symbol="RELIANCE",
        company="Reliance Industries",
        title="RIL shares rise 2% as strong O2C growth lifts Q2 earnings outlook",
        body="Reliance Industries reported stronger-than-expected O2C segment growth in its "
        "quarterly update, prompting brokerages to raise earnings estimates.",
        must_not_invent=("Rs 500 crore", "Aramco"),
    ),
    # --- follow-up / developing ---
    Article(
        label="developing-followup",
        publisher="outlookbusiness.com",
        symbol="TMCV",
        company="Tata Motors",
        title="Tata Motors Iveco deal: acceptance period for takeover offer to open next week",
    ),
)
