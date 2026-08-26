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


"""Everything that shells out to `gh`."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from charm_tech_code.ai_failure_notifier import markers as _markers
from charm_tech_code.ai_failure_notifier import summary as _summary
from charm_tech_code.ai_failure_notifier.constants import MARKER_PREFIX, RECENT_ISSUE_SCAN
from charm_tech_code.ai_failure_notifier.models import CandidateIssue, FailedJob


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a `gh` subcommand, returning the completed process."""
    # S607: `gh` is deliberately called by name, resolved from the runner's PATH.
    return subprocess.run(['gh', *args], text=True, capture_output=True, check=check)  # noqa: S607


def gh_json(*args: str) -> Any:
    """Run a `gh ... --json ...` subcommand and parse its stdout as JSON."""
    result = gh(*args)
    return json.loads(result.stdout) if result.stdout.strip() else None


def fetch_failed_jobs(repo: str, run_id: str) -> list[FailedJob]:
    """List the failed jobs of a run, each with its id, name, and failed step."""
    data = gh_json('run', 'view', str(run_id), '--repo', repo, '--json', 'jobs') or {}
    failed: list[FailedJob] = []
    for job in data.get('jobs', []):
        if job.get('conclusion') != 'failure':
            continue
        failed_step = None
        for step in job.get('steps') or []:
            if step.get('conclusion') == 'failure':
                failed_step = step.get('name')
                break
        failed.append(FailedJob(id=job['databaseId'], name=job['name'], failed_step=failed_step))
    return failed


def fetch_job_log(repo: str, run_id: str, job_id: int) -> str:
    """Fetch one job's full log text.

    Uses the REST logs endpoint rather than `gh run view --log`: the latter
    exits 0 with empty stdout on some `gh` builds (reproduced on 2.45.0), which
    silently degrades the extracted signature to nothing. An empty log here is
    reported rather than swallowed.

    `--allow-escape-sequences` is not optional. From gh 2.9x, `gh api` refuses
    to write a response containing terminal escapes -- "the response contains
    terminal escape sequences; pass --allow-escape-sequences to output it
    anyway" -- and returns nothing at all. Actions logs are full of them; ANSI
    above exists to strip them. Runners carry a gh new enough to refuse (2.97.0
    when this was measured, in fork run 32673538357), so without the flag every
    fetch comes back empty and the signature degrades to the job name.

    Older builds have no such check and no such flag, and reject it as unknown
    rather than ignoring it, so those retry without.
    """
    endpoint = f'repos/{repo}/actions/jobs/{job_id}/logs'
    result = gh('api', endpoint, '--allow-escape-sequences', check=False)
    if 'unknown flag' in (result.stderr or ''):
        result = gh('api', endpoint, check=False)
    if not result.stdout.strip():
        # `gh` puts the status on stderr ("gh: Not Found (HTTP 404)"), and the
        # exit code alone is 1 for all of them. Without the status there is no
        # telling a log that is not ready yet from a token that has lost
        # `actions: read`, and the two want opposite fixes.
        detail = ' '.join((result.stderr or '').split())[:200] or 'no stderr'
        _summary.write_step_summary(
            f'Warning: no log text for job {job_id} of run {run_id} '
            f'(gh exit {result.returncode}: {detail}); '
            f'signature will be based on the job name alone.'
        )
    return result.stdout


def fetch_run_meta(repo: str, run_id: str) -> dict[str, str]:
    """Fetch a run's display metadata (title, workflow name, url, createdAt)."""
    return (
        gh_json(
            'run',
            'view',
            str(run_id),
            '--repo',
            repo,
            '--json',
            'displayTitle,workflowName,url,createdAt',
        )
        or {}
    )


def search_issue_numbers(repo: str, query_text: str) -> list[int]:
    """Search issues (any state) in `repo` for `query_text`, return issue numbers."""
    # The repo must be passed as `--repo`, not folded into the positional query.
    # `gh search issues` quotes each positional argument as a single search
    # keyword, so `repo:owner/name "text"` becomes the literal keyword
    # `repo:"owner/name \"text\""` and GitHub rejects it as an invalid query.
    data = (
        gh_json(
            'search', 'issues', '--repo', repo, '--limit', '10', '--json', 'number', query_text
        )
        or []
    )
    return [item['number'] for item in data]


def fetch_issue_texts(repo: str, number: int) -> list[str]:
    """Fetch an issue's body plus all comment bodies, for marker scanning."""
    data = gh_json('issue', 'view', str(number), '--repo', repo, '--json', 'body,comments') or {}
    texts = [data.get('body') or '']
    for c in data.get('comments') or []:
        texts.append(c.get('body') or '')
    return texts


def recent_issue_texts(repo: str, limit: int = RECENT_ISSUE_SCAN) -> list[tuple[int, str]]:
    """Return (number, text) pairs for the `limit` most recently updated issues.

    Bodies and comment bodies both, since a notifier marker with
    `origin=comment` lives in a comment rather than the body.
    """
    data = (
        gh_json(
            'issue',
            'list',
            '--repo',
            repo,
            '--state',
            'all',
            '--limit',
            str(limit),
            '--json',
            'number,body,comments',
        )
        or []
    )
    texts: list[tuple[int, str]] = []
    for issue in data:
        number = issue['number']
        texts.append((number, issue.get('body') or ''))
        for comment in issue.get('comments') or []:
            texts.append((number, comment.get('body') or ''))
    return texts


def locate_run_markers(repo: str, run_id: str) -> tuple[int | None, str | None, int | None]:
    """Find the markers belonging to `run_id` and classify them.

    Scans the most recently updated issues first, and only falls back to
    `gh search issues` if that finds nothing.

    The ordering matters, and is the whole point of doing it this way. The
    notifier stamps its marker moments before this workflow runs, and GitHub's
    issue *search* index is not read-your-writes -- a marker that has not been
    indexed yet reads as "no notifier marker found", and main() responds by
    opening a *second* issue for a run that already has one. The issue *list*
    endpoint has no such lag, and the artefact the notifier just touched is by
    construction among the most recently updated issues in the repo.

    Search remains as a fallback for the one case the list cannot cover: a repo
    busy enough that more than `RECENT_ISSUE_SCAN` issues were updated in
    between, where a stale index still beats no lookup at all.
    """
    markers = _markers.find_run_markers(recent_issue_texts(repo), run_id)
    if markers != (None, None, None):
        return markers

    hits = search_issue_numbers(repo, f'{MARKER_PREFIX}:run={run_id}')
    texts: list[tuple[int, str]] = []
    for number in hits:
        for text in fetch_issue_texts(repo, number):
            texts.append((number, text))
    return _markers.find_run_markers(texts, run_id)


def resolve_origin(
    repo: str, run_id: str, notify_issue: int | None, notify_origin: str | None
) -> tuple[int | None, str | None, int | None]:
    """Work out which artefact this run should upgrade.

    Returns the same triple as `find_run_markers`.

    When the notifier tells us the issue it created or commented on, that is
    authoritative for `origin_issue`/`origin_kind` and we never search for it.
    That removes the read-your-writes hazard `locate_run_markers` exists to
    work around: the notifier stamps its marker moments before this job runs,
    and GitHub's issue *search* index lags, so a marker that has not been
    indexed yet reads as "no notifier marker found" and main() opens a second
    issue for a run that already has one. A number passed directly through the
    workflow cannot be stale.

    Rung zero still needs a lookup, and the notifier's output cannot supply
    it: "this run id was already fully enriched" is a fact about an *earlier
    run of this script*, not about what the notifier just did. But knowing the
    issue narrows that lookup from a scan of the repo's recently-updated
    issues to reading the one issue we were handed.

    With no `notify_issue` -- the notifier failed, or a caller has not been
    migrated -- this falls back to the original repo-wide scan, so the script
    still works when it is not told anything.
    """
    if notify_issue is None:
        return locate_run_markers(repo, run_id)

    texts = [(notify_issue, text) for text in fetch_issue_texts(repo, notify_issue)]
    enriched_issue, origin_kind, origin_issue = _markers.find_run_markers(texts, run_id)
    # The passed-in values win: a marker we failed to find on the issue does
    # not make the issue the wrong one.
    return enriched_issue, notify_origin or origin_kind, notify_issue


def search_candidates(
    repo: str, workflow_name: str
) -> tuple[list[CandidateIssue], list[CandidateIssue]]:
    """Coarse candidate search: open and closed issues matching the workflow name."""
    fields = 'number,title,body,createdAt,closedAt'
    open_issues = (
        gh_json(
            'issue',
            'list',
            '--repo',
            repo,
            '--state',
            'open',
            '--search',
            f'"{workflow_name}"',
            '--json',
            fields,
            '--limit',
            '20',
        )
        or []
    )
    closed_issues = (
        gh_json(
            'issue',
            'list',
            '--repo',
            repo,
            '--state',
            'closed',
            '--search',
            f'"{workflow_name}"',
            '--json',
            fields,
            '--limit',
            '20',
        )
        or []
    )
    return (
        [CandidateIssue.from_gh(i) for i in open_issues],
        [CandidateIssue.from_gh(i) for i in closed_issues],
    )


def existing_labels(repo: str) -> set[str]:
    """Return the set of label names that already exist in `repo`."""
    data = gh_json('label', 'list', '--repo', repo, '--json', 'name', '--limit', '100') or []
    return {item['name'] for item in data}


def filter_labels(labels: list[str], available: set[str]) -> list[str]:
    """Drop labels that don't already exist in the repo (never auto-create)."""
    return [label for label in labels if label in available]
