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

__all__ = ["CompanyContext", "CoverageTier", "context_for"]


class CoverageTier(Enum):
    """How much of the signal universe we actually cover for a company."""

    FULL = "FULL"
    LIMITED = "LIMITED"


@dataclass(frozen=True)
class CompanyContext:
    symbol: str
    name: str
    tier: CoverageTier


# The demo set: depth over breadth (DESIGN.md D19). Everything else is LIMITED, and
# says so rather than being served badly.
_CURATED: dict[str, str] = {
    "TATAMOTORS": "Tata Motors Limited",
    "RELIANCE": "Reliance Industries Limited",
    "INFY": "Infosys Limited",
    "TCS": "Tata Consultancy Services Limited",
    "HDFCBANK": "HDFC Bank Limited",
    "HINDALCO": "Hindalco Industries Limited",
    "ITC": "ITC Limited",
    "SBIN": "State Bank of India",
}


def context_for(symbol: str, name: str) -> CompanyContext:
    """Context for a security. Unknown symbols are LIMITED, never refused."""
    if symbol in _CURATED:
        return CompanyContext(symbol=symbol, name=_CURATED[symbol], tier=CoverageTier.FULL)
    return CompanyContext(symbol=symbol, name=name, tier=CoverageTier.LIMITED)
