"""Where a report came from, as a standing a reader can see at a glance.

Two reports can say the same thing and deserve very different weight. An exchange filing
is the company speaking on the record. A national business daily is a newsroom with an
editor and something to lose. A press-release wire is distribution — the company's own
words, carried verbatim, with no one checking them. An aggregator nobody has heard of is
none of those.

The tier on each evidence record already carries some of this (VISION §12), but a tier is
a scoring input and this is a *label*: the thing a reader glances at before deciding
whether to open a story.

**Not "verified".** We verify nothing about a publisher. What we can defend is whether an
outlet is one we recognise, and that is exactly what this says. ``UNRECOGNISED`` means
*absent from a curated list*, never *untrustworthy* — a real story broken by an outlet we
have not catalogued is a real story, and the corroboration model is what promotes it
(D13), not this label.

Curated one publisher at a time, like the company aliases in ``context`` and the focus
vocabulary in ``focus``. A registry generated from whatever appeared in a feed would
launder the feed's own biases into a trust signal.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

from .models import SourceTier

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import Evidence

__all__ = [
    "ESTABLISHED_PUBLISHERS",
    "RELEASE_WIRES",
    "SourceStanding",
    "standing_label",
    "standing_of",
    "standing_of_publisher",
]


class SourceStanding(Enum):
    """What kind of source a report came from. Ordered strongest first."""

    OFFICIAL = "OFFICIAL"
    """Filed with the exchange or issued by a regulator. Disclosed, not reported."""
    ESTABLISHED = "ESTABLISHED"
    """A news organisation we recognise: a wire service or an established outlet."""
    SYNDICATED_RELEASE = "SYNDICATED_RELEASE"
    """A press-release wire. The company's own words, distributed verbatim — which is a
    different thing from a newsroom reporting them, and worth saying so."""
    UNRECOGNISED = "UNRECOGNISED"
    """Not a publisher we hold a record of. An absence in our list, not a verdict."""
    COMPUTED = "COMPUTED"
    """Our own measurement from price data. It has no publisher, and saying it is an
    exchange filing would claim an authority we do not have."""


_LABELS: dict[SourceStanding, str] = {
    SourceStanding.OFFICIAL: "exchange filing",
    SourceStanding.ESTABLISHED: "established outlet",
    SourceStanding.SYNDICATED_RELEASE: "press release",
    SourceStanding.UNRECOGNISED: "unrecognised publisher",
    SourceStanding.COMPUTED: "our own measurement",
}


def standing_label(standing: SourceStanding) -> str:
    """The reader's words for a standing. Descriptive, never a rating."""
    return _LABELS[standing]


ESTABLISHED_PUBLISHERS: frozenset[str] = frozenset(
    {
        # Wire services.
        "reuters",
        "bloomberg",
        "associated press",
        "afp",
        "pti",
        "press trust of india",
        "ani",
        "asian news international",
        "ians",
        # Indian business and financial press.
        "the economic times",
        "economic times",
        "et now",
        "et auto",
        "etmarkets.com",
        "business standard",
        "businessline",
        "the hindu businessline",
        "thehindubusinessline.com",
        "the hindu",
        "livemint",
        "mint",
        "moneycontrol",
        "moneycontrol.com",
        "cnbc tv18",
        "cnbctv18",
        "ndtv profit",
        "business today",
        "financial express",
        "financialexpress.com",
        "the financial express",
        "fortune india",
        "fortuneindia.com",
        "outlook business",
        "outlookbusiness.com",
        "bw businessworld",
        "free press journal",
        "freepressjournal.in",
        "the indian express",
        "times now",
        "timesnownews.com",
        "the times of india",
        "times of india",
        "mid-day",
        "inc42",
        "rediff moneywiz",
        # National broadcasters and state news services.
        "ddnews.gov.in",
        "newsonair.gov.in",
        "news on air",
        "etv bharat",
        # International outlets that cover Indian listings.
        "marketwatch",
        "the globe and mail",
        "yahoo finance singapore",
        "ibtimes india",
        "the manila times",
        # Legal and tax trade press, for regulatory and court reporting.
        "scc online",
        "livelawbiz",
        "taxscan",
        "juris hour",
    }
)
"""Publishers we recognise. Short, curated, and certainly incomplete.

Incompleteness is the stated limitation rather than a hidden one: an outlet missing from
this set is labelled unrecognised, which is accurate — we do not recognise it — and is why
the label is descriptive rather than a rating.
"""

RELEASE_WIRES: frozenset[str] = frozenset(
    {
        "pr newswire",
        "globenewswire",
        "business wire",
        "businesswire",
        "newmediawire",
        "tmx newsfile",
        "ntb kommunikasjon",
        "accesswire",
        "prnewswire",
    }
)
"""Press-release distribution. Carries a company's own statement, unedited.

Separated from established outlets deliberately. A release is closer to a primary source
than an aggregator is, and further from journalism than a newsroom report — collapsing it
into either direction would lose the distinction a reader most needs here.
"""

_NOISE = re.compile(r"\s+[-|·—]\s+.*$")
"""A trailing section or edition suffix — "The Hindu - Business".

The separator must be *surrounded* by whitespace. Without that, this ate the second half
of every hyphenated masthead: "Mid-Day" became "mid" and stopped being recognised, which
is precisely the silent mislabelling this registry exists to avoid.
"""


def _normalise(publisher: str) -> str:
    """Lowercase, trimmed, and without a trailing section or edition suffix."""
    return _NOISE.sub("", publisher.strip().lower()).strip()


def standing_of_publisher(publisher: str, tier: SourceTier) -> SourceStanding:
    """One evidence record's standing.

    The tier decides first: an exchange filing is official whoever relayed it. Only then
    does the publisher registry get a say.
    """
    if tier is SourceTier.OFFICIAL_DISCLOSURE:
        return SourceStanding.OFFICIAL
    name = _normalise(publisher)
    if name in RELEASE_WIRES:
        return SourceStanding.SYNDICATED_RELEASE
    if name in ESTABLISHED_PUBLISHERS:
        return SourceStanding.ESTABLISHED
    return SourceStanding.UNRECOGNISED


_ORDER: tuple[SourceStanding, ...] = (
    SourceStanding.OFFICIAL,
    SourceStanding.ESTABLISHED,
    SourceStanding.SYNDICATED_RELEASE,
    SourceStanding.UNRECOGNISED,
)
"""Strongest first, for picking an event's standing from the evidence behind it."""


def standing_of(evidence: Iterable[Evidence]) -> SourceStanding:
    """An event's standing: the strongest thing backing it.

    Strongest rather than an average, because an event supported by a filing *and* an
    aggregator is supported by a filing. The weaker source does not dilute the stronger
    one; it simply adds nothing.

    Computed evidence — our own market observations — is set aside, and an event with
    nothing but computed evidence says so. It has no publisher, so calling it unrecognised
    would be wrong and calling it official would claim an authority we do not have.
    """
    reported = [e for e in evidence if e.tier is not SourceTier.COMPUTED]
    if not reported:
        return SourceStanding.COMPUTED
    found = {standing_of_publisher(e.publisher, e.tier) for e in reported}
    return next(standing for standing in _ORDER if standing in found)
