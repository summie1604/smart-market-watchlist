"""Adapters — everything that talks to the outside world.

Each implements a protocol from :mod:`smart_watchlist.core.ports`. Domain logic is
shaped by the protocol, never by a provider's response format, which is what makes a
source substitution a swap rather than a rewrite.
"""

__all__: list[str] = []
