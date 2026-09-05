"""Independent-source counting — D13.

Ten outlets running one agency's wire copy is one source, not ten. Counting articles
would let syndication manufacture confidence, which corrupts the confidence axis the
whole trust story rests on.

So two quantities are tracked and only the second is evidence:

    article_count            how many reports we hold
    independent_source_count how many independent publishers they represent

The syndication map is bounded and hand-maintained on purpose. A general media
provenance graph is not this project's problem, and pretending the map is complete
would be worse than admitting it is not: **corroboration is evidence about independent
reporting, never a measurement of truth.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import Evidence

__all__ = ["SOURCE_FAMILIES", "Corroboration", "assess_corroboration", "family_of"]

SOURCE_FAMILIES: dict[str, str] = {
    # Wire services and the outlets that most visibly carry their copy verbatim.
    "pti": "wire:pti",
    "press trust of india": "wire:pti",
    "ani": "wire:ani",
    "asian news international": "wire:ani",
    "ians": "wire:ians",
    "reuters": "wire:reuters",
    "bloomberg": "wire:bloomberg",
    "afp": "wire:afp",
    "associated press": "wire:ap",
    # Same newsroom, several surfaces.
    "the economic times": "group:et",
    "economic times": "group:et",
    "etmarkets.com": "group:et",
    "ethrworld.com": "group:et",
    "the times of india": "group:toi",
    "times of india": "group:toi",
    "moneycontrol": "group:network18",
    "cnbctv18": "group:network18",
    "news18": "group:network18",
    "livemint": "group:mint",
    "mint": "group:mint",
    "business standard": "group:bs",
    "the hindu businessline": "group:hindu",
    "the hindu": "group:hindu",
}
"""Publishers known to share a newsroom or a wire. Deliberately short.

Everything absent is treated as independent, which is the honest default and also the
limitation: **unknown syndication inflates the independent count**, and nothing here
detects it."""


@dataclass(frozen=True)
class Corroboration:
    """How many genuinely separate reporters support an event."""

    article_count: int
    independent_source_count: int
    families: tuple[str, ...]
    has_authoritative: bool
    """True when at least one piece of evidence is an exchange filing or equivalent."""

    @property
    def is_corroborated(self) -> bool:
        """Two or more independent sources, or one authoritative one.

        A filing needs no corroboration — the company said it to the exchange.
        """
        return self.has_authoritative or self.independent_source_count >= 2

    @property
    def summary(self) -> str:
        """The line the UI shows instead of N duplicate headlines."""
        articles = f"{self.article_count} article{'s' if self.article_count != 1 else ''}"
        sources = (
            f"{self.independent_source_count} independent "
            f"source{'s' if self.independent_source_count != 1 else ''}"
        )
        return f"{articles} · {sources}"


def family_of(publisher: str) -> str:
    """The source family a publisher belongs to, or the publisher itself.

    An unmapped publisher is its own family — independent until shown otherwise, and the
    map is known to be incomplete.
    """
    normalised = re.sub(r"[^a-z0-9. ]", "", publisher.lower()).strip()
    return SOURCE_FAMILIES.get(normalised, f"publisher:{normalised or 'unknown'}")


def assess_corroboration(evidence: Iterable[Evidence]) -> Corroboration:
    """Count reports and the independent sources behind them."""
    from .models import SourceTier

    items = list(evidence)
    families = {family_of(e.publisher) for e in items if e.tier is not SourceTier.COMPUTED}
    return Corroboration(
        article_count=len(items),
        independent_source_count=len(families),
        families=tuple(sorted(families)),
        has_authoritative=any(e.tier is SourceTier.OFFICIAL_DISCLOSURE for e in items),
    )
