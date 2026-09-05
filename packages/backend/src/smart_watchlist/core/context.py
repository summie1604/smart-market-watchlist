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
_CURATED: dict[str, tuple[str, str]] = {
    "RELIANCE": ("Reliance Industries Limited", "^NSEI"),
    "INFY": ("Infosys Limited", "^CNXIT"),
    "TCS": ("Tata Consultancy Services Limited", "^CNXIT"),
    "HDFCBANK": ("HDFC Bank Limited", "^NSEBANK"),
    "SBIN": ("State Bank of India", "^NSEBANK"),
    "HINDALCO": ("Hindalco Industries Limited", "^CNXMETAL"),
    "ITC": ("ITC Limited", "^CNXFMCG"),
    "TMPV": ("Tata Motors Passenger Vehicles Limited", "^CNXAUTO"),
    "TMCV": ("Tata Motors Limited", "^CNXAUTO"),
}


def context_for(symbol: str, name: str) -> CompanyContext:
    """Context for a security. Unknown symbols are LIMITED, never refused."""
    curated = _CURATED.get(symbol)
    if curated is not None:
        curated_name, sector_index = curated
        return CompanyContext(
            symbol=symbol,
            name=curated_name,
            tier=CoverageTier.FULL,
            sector_index=sector_index,
        )
    return CompanyContext(symbol=symbol, name=name, tier=CoverageTier.LIMITED)


def curated_symbols() -> tuple[str, ...]:
    """The securities the market pipeline observes each run."""
    return tuple(_CURATED)
