"""Judge mode — a deterministic market scenario, seeded through the real pipelines.

Nothing here is a second engine, a second store or a fake card. The fixtures are
*sources*: they implement the same adapter protocols the live providers implement, and
`seed` runs the ordinary ingestion cycle over them. Every attention level, reason code,
coverage record, watch-point trigger and assistant answer a judge sees is produced by the
same deterministic code that runs in production (D42).

The only simulated part is the market scenario.
"""

from .scenario import SCENARIO, ScenarioCompany
from .seed import JUDGE_MARKER, judge_db_path, reset, seed, seeded

__all__ = [
    "JUDGE_MARKER",
    "SCENARIO",
    "ScenarioCompany",
    "judge_db_path",
    "reset",
    "seed",
    "seeded",
]
