"""Company context — what each company is exposed to, and how well we cover it.

Step 0 carries only the coverage tier, because that is the only context the disclosure
path consults. Sector, competitors, commodities, currencies and regulatory exposure
arrive with the relevance work in step 3 (DESIGN.md D11).

Curated deliberately: relevance is only as good as this, and a model guessing at a
company's exposures is exactly the unverifiable context the vision refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["BROAD_INDEX", "CompanyContext", "CoverageTier", "context_for", "curated_symbols"]


class CoverageTier(Enum):
    """How much of the signal universe we actually cover for a company."""

    FULL = "FULL"
    LIMITED = "LIMITED"


@dataclass(frozen=True)
class CompanyContext:
    symbol: str
    name: str
    tier: CoverageTier
    aliases: tuple[str, ...] = ()
    """Names this company is called in a headline — canonical, ticker, curated short form.

    Curated, never inferred. A name derived from arbitrary text is a name we cannot
    defend, and a wrong one attributes another company's event to this one.
    """
    sector_index: str | None = None
    """The index a move is judged against, so broad-market movement is not read as
    company-specific. ``None`` means we have no sector reference and must say so rather
    than falling back to the broad index and implying a comparison we did not make."""


BROAD_INDEX = "^NSEI"
"""NIFTY 50 — the fallback reference, used only where no sector index is curated."""

# The demo set: depth over breadth (DESIGN.md D19). Everything else is LIMITED, and
# says so rather than being served badly.
#
# TATAMOTORS is deliberately absent: it demerged into TMPV and TMCV and no longer
# resolves as a security. Carrying a dead symbol would have produced a permanent,
# unexplained market-coverage gap for a company we claim to cover fully.
_CURATED: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "RELIANCE": (
        "Reliance Industries Limited",
        "^NSEI",
        ("Reliance Industries", "Reliance", "RIL"),
    ),
    "INFY": ("Infosys Limited", "^CNXIT", ("Infosys",)),
    "TCS": (
        "Tata Consultancy Services Limited",
        "^CNXIT",
        ("Tata Consultancy Services", "TCS"),
    ),
    "HDFCBANK": ("HDFC Bank Limited", "^NSEBANK", ("HDFC Bank",)),
    "SBIN": ("State Bank of India", "^NSEBANK", ("State Bank of India", "SBI")),
    "HINDALCO": ("Hindalco Industries Limited", "^CNXMETAL", ("Hindalco Industries", "Hindalco")),
    "ITC": ("ITC Limited", "^CNXFMCG", ("ITC",)),
    "TMPV": (
        "Tata Motors Passenger Vehicles Limited",
        "^CNXAUTO",
        ("Tata Motors Passenger Vehicles", "Tata Motors"),
    ),
    "TMCV": ("Tata Motors Limited", "^CNXAUTO", ("Tata Motors",)),
}
"""Curated universe: canonical name, sector index, and the aliases a headline may use.

Short aliases are a judgement with a stated risk. "Reliance" is included because the vast
majority of headlines in that feed mean Reliance Industries, and excluding it would reject
most genuine coverage — but other listed companies share the word, so a headline about one
of them could be accepted. The subject-position rules below remove the common cases
(counterparty, list, roundup); the residual risk is accepted deliberately rather than
hidden, and it is the reason short aliases are curated one at a time instead of generated.
"""


def context_for(symbol: str, name: str) -> CompanyContext:
    """Context for a security. Unknown symbols are LIMITED, never refused."""
    curated = _CURATED.get(symbol)
    if curated is not None:
        curated_name, sector_index, aliases = curated
        return CompanyContext(
            symbol=symbol,
            name=curated_name,
            tier=CoverageTier.FULL,
            sector_index=sector_index,
            aliases=(symbol, curated_name, *aliases),
        )
    # Outside the curated universe there are no vetted aliases, so the only name we can
    # defend is the one we were given.
    return CompanyContext(symbol=symbol, name=name, tier=CoverageTier.LIMITED, aliases=(symbol,))


def curated_symbols() -> tuple[str, ...]:
    """The securities the market pipeline observes each run."""
    return tuple(_CURATED)
