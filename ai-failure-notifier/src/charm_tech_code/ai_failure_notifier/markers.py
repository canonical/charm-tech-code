# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""The HTML comment markers the two workflows communicate through."""

from __future__ import annotations

import hashlib
from typing import Literal

from charm_tech_code.ai_failure_notifier.constants import MARKER_PREFIX, MARKER_RE
from charm_tech_code.ai_failure_notifier.models import RunSignature

# --- Marker + signature hashing ---


def signature_hash(signature: RunSignature) -> str:
    """Deterministic short fingerprint of a run signature.

    Used only for the marker's :sig= suffix (not for dedup decisions --
    that's the LLM's job, guided by the candidate pool).
    """
    parts: list[str] = []
    for job in signature.jobs:
        parts.extend(failure.test for failure in job.pytest_failures)
        parts.extend(job.go_failures)
        if job.traceback_top_error:
            parts.append(job.traceback_top_error)
        if job.failed_step:
            parts.append(job.failed_step)
    canonical = '\n'.join(sorted(parts)) or signature.workflow_name
    return hashlib.sha1(canonical.encode('utf-8'), usedforsecurity=False).hexdigest()[:16]


# Which artefact the notifier touched: a fresh placeholder issue, or a comment
# on an issue that already existed. A Literal so a type checker rejects a bad
# value before it reaches a marker.
Origin = Literal['new', 'comment']


def render_notifier_marker(run_id: str, origin: Origin) -> str:
    """Render the marker the notifier stamps, telling the enricher what it touched."""
    return f'<!-- {MARKER_PREFIX}:run={run_id}:origin={origin} -->'


def render_enriched_marker(run_id: str, signature: RunSignature) -> str:
    """Render the marker this script stamps once it has fully processed a run.

    Presence of :sig= is what makes rung zero (find_run_markers) treat a later
    same-run-id trigger as "already enriched, just note the re-run".
    """
    return f'<!-- {MARKER_PREFIX}:run={run_id}:sig={signature_hash(signature)} -->'


def find_run_markers(
    texts: list[tuple[int, str]], run_id: str
) -> tuple[int | None, str | None, int | None]:
    """Scan (issue_number, text) pairs for markers belonging to `run_id`.

    Returns (enriched_issue, origin_kind, origin_issue):
    - enriched_issue: an issue number carrying a :sig= marker for this run
      (rung zero -- this run was already fully enriched once), else None.
    - origin_kind / origin_issue: the "new"/"comment" marker the notifier
      stamped for this run (identifies which artefact to upgrade), else
      (None, None).
    """
    run_id = str(run_id)
    enriched_issue = None
    origin_kind = None
    origin_issue = None
    for number, text in texts:
        if not text:
            continue
        for match in MARKER_RE.finditer(text):
            if match['run_id'] != run_id:
                continue
            if match['sig']:
                enriched_issue = number
            elif match['origin']:
                origin_kind = match['origin']
                origin_issue = number
    return enriched_issue, origin_kind, origin_issue
