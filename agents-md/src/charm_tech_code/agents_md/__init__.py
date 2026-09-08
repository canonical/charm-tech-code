"""Keep the estate's AGENTS.md files honest.

Three checks and one fix, plus the per-repo question batteries they read.
The design they implement is `agents-md-validation.md` in the repo-setup
notes: layer 1 is deterministic staleness detection, layer 2 is the
behavioural battery. The agent-facing half lives in the
`charm-tech-baseline` skill in `canonical/charm-tech`.
"""

from .cli import main

__all__ = ['main']
