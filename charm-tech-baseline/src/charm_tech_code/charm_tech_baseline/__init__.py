"""Audit a repository against the Canonical Charm Tech baseline.

The agent-facing half of this lives in the `charm-tech-baseline` skill in
`canonical/charm-tech`; this package is the deterministic half it drives.
"""

from .cli import main

__all__ = ['main']
