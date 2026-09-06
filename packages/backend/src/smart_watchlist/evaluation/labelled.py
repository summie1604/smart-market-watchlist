"""Human labels for the attention engine.

**Deliberately empty.** Each case is one real assessment a person read, with the level
they think it should have had and why. Filling this in requires sitting with the record;
it cannot be generated, and generating it would defeat the point of measuring.

To add a case: take an ``event_id`` from `/v1/assessments`, read the development and its
evidence, and record the level you would have wanted as a reader — not the one you think
the engine would give.

    LabelledCase(
        event_id="c8d30963357a7d90",
        symbol="TMPV",
        description="Tata Motors launches tender offer for Iveco",
        expected=Attention.HIGH,
        note="Company-transforming acquisition, four independent publishers, filed.",
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .attention import LabelledCase

__all__ = ["LABELLED"]

LABELLED: tuple[LabelledCase, ...] = ()
"""No cases yet. See ``docs/status.md`` — this gap is stated, not hidden."""
