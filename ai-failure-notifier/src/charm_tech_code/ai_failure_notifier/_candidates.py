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

from ._constants import CLOSED_CANDIDATE_WINDOW_DAYS, MAX_CANDIDATES, MAX_SIGNATURE_CHARS
from ._markers import parse_signature_stamp
from ._models import CandidateIssue

# The order the fields are shown in, and what each is called in the block. The
# names match the prompt's own vocabulary for the rungs ("pytest_failures[].test",
# "the top error class", "the same failed_step") so that the model is being
# shown the thing the instruction names.
_SIGNATURE_FIELDS = ('tests', 'errors', 'steps', 'jobs')


def within_window(iso_timestamp: str, now: datetime.datetime, days: int) -> bool:
    """Return whether `iso_timestamp` falls within `days` of `now`."""
    ts = datetime.datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
    return now - ts <= datetime.timedelta(days=days)


def render_signature_line(issue: CandidateIssue) -> str | None:
    """The candidate's own failure signature, if this tool has ever stamped one.

    Read from the hidden stamp the enricher writes into every artefact it
    creates -- body first, then each comment, most recent stamp wins. An issue
    the tool hasn't enriched has no stamp and gets no line, so for those the
    body excerpt and comments are the only evidence.
    """
    stamp = None
    for text in (issue.body or '', *issue.comments):
        stamp = parse_signature_stamp(text) or stamp
    if not stamp:
        return None
    parts = []
    for key in _SIGNATURE_FIELDS:
        values = [str(v) for v in (stamp.get(key) or []) if v]
        if values:
            parts.append(f'{key} {", ".join(values)}')
    if not parts:
        return None
    run = stamp.get('run')
    prefix = f'failure signature (run {run}): ' if run else 'failure signature: '
    return (prefix + '; '.join(parts))[:MAX_SIGNATURE_CHARS]


def render_candidate(issue: CandidateIssue, state: str) -> str:
    """One candidate's entry: the headline, then its `>` evidence lines."""
    lines = [f'- **#{issue.number} — {issue.title}** {state}', f'  > {issue.excerpt()}']
    signature_line = render_signature_line(issue)
    if signature_line:
        lines.append(f'  > {signature_line}')
    comments = issue.recent_comments()
    for i, comment in enumerate(comments):
        label = 'most recent comment' if i == len(comments) - 1 else 'earlier comment'
        lines.append(f'  > {label}: {comment}')
    return '\n'.join(lines)


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

    Each entry carries whatever evidence of what the issue is *about* exists:
    the body excerpt, this tool's own signature stamp if it has ever enriched
    that issue, and the most recent comments. An automatically-opened issue's
    body is the single line "Scheduled workflow 'X' failed: <url>", so for
    those the stamp and the comments are the only places a test id or an error
    class can come from, and without them the prompt's strong rung can't fire.
    """
    entries: list[str] = []
    for issue in open_issues:
        if len(entries) >= MAX_CANDIDATES:
            break
        entries.append(render_candidate(issue, '(open)'))

    recent_closed = [
        i
        for i in closed_issues
        if i.closed_at and within_window(i.closed_at, now, CLOSED_CANDIDATE_WINDOW_DAYS)
    ]
    for issue in recent_closed:
        if len(entries) >= MAX_CANDIDATES:
            break
        entries.append(
            render_candidate(
                issue,
                f'(closed {issue.closed_at} -- recently closed; treat as at most a '
                'medium-confidence match)',
            )
        )

    if not entries:
        return '(no open issues found for this workflow)'
    return '\n'.join(entries)
