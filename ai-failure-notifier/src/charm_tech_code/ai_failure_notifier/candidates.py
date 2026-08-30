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


"""Building the pool of issues a failure might already have."""

from __future__ import annotations

import datetime

from charm_tech_code.ai_failure_notifier.constants import (
    CLOSED_CANDIDATE_WINDOW_DAYS,
    MAX_CANDIDATES,
)
from charm_tech_code.ai_failure_notifier.models import CandidateIssue


def within_window(iso_timestamp: str, now: datetime.datetime, days: int) -> bool:
    """Return whether `iso_timestamp` falls within `days` of `now`."""
    ts = datetime.datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
    return now - ts <= datetime.timedelta(days=days)


def build_candidates_block(
    open_issues: list[CandidateIssue],
    closed_issues: list[CandidateIssue],
    now: datetime.datetime,
) -> str:
    """Render the {{CANDIDATES_BLOCK}} the prompt expects.

    Up to MAX_CANDIDATES entries: open issues first, then recently-closed
    issues (<=14 days) filling any remaining slots, explicitly labelled as
    closed so the LLM never auto-treats one as a strong match. Calibration on
    past scheduled failures found a closed issue can corroborate a match but
    should never be enough to dedupe against on its own.
    """
    entries: list[str] = []
    for issue in open_issues:
        if len(entries) >= MAX_CANDIDATES:
            break
        entries.append(f'- **#{issue.number} — {issue.title}** (open)\n  > {issue.excerpt()}')

    recent_closed = [
        i
        for i in closed_issues
        if i.closed_at and within_window(i.closed_at, now, CLOSED_CANDIDATE_WINDOW_DAYS)
    ]
    for issue in recent_closed:
        if len(entries) >= MAX_CANDIDATES:
            break
        entries.append(
            f'- **#{issue.number} — {issue.title}** (closed {issue.closed_at} -- '
            f'recently closed; treat as at most a medium-confidence match)\n  > {issue.excerpt()}'
        )

    if not entries:
        return '(no open issues found for this workflow)'
    return '\n'.join(entries)
