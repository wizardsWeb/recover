"""Step 8 — Learn: no-op in Phase 4.

The step exists now, empty, on purpose. The loop's shape is the deliverable of
this phase, and a loop with eight steps and a gap where learning goes would let
the later phases each invent their own place to put reward updates. This is that
place.
"""

from typing import Any


async def run_learn(case: dict[str, Any], outcome: str, decision: dict[str, Any]) -> None:
    """No-op in Phase 4.

    Phase 6 wires contextual bandit reward updates here.
    Phase 9 wires uplift model training data here.
    Phase 10 wires federated network stat aggregation here.
    """
    return None
