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


"""Entry point."""

from __future__ import annotations

import dataclasses
import datetime
import os
import sys
from typing import Any

from charm_tech_code.ai_failure_notifier import github, openrouter, prompt, summary
from charm_tech_code.ai_failure_notifier.apply import apply_entry, plain_fallback_body, render_body
from charm_tech_code.ai_failure_notifier.candidates import build_candidates_block
from charm_tech_code.ai_failure_notifier.constants import DEFAULT_MODEL, MARKER_PREFIX
from charm_tech_code.ai_failure_notifier.envelope import normalise_envelope, validate_envelope
from charm_tech_code.ai_failure_notifier.markers import render_enriched_marker
from charm_tech_code.ai_failure_notifier.models import RunSignature
from charm_tech_code.ai_failure_notifier.signatures import build_job_signature, build_run_signature


@dataclasses.dataclass(frozen=True)
class _RunConfig:
    """The environment `main` runs with, read once up front."""

    repo: str
    run_id: str
    workflow_name: str
    run_url: str
    api_key: str
    model: str
    # What the notifier did, when it tells us. Both are optional: an
    # unmigrated caller, or a notifier that failed before it got as far as an
    # issue, leaves them empty and we go looking instead.
    notify_issue: int | None
    notify_origin: str | None


def _read_config() -> _RunConfig:
    """Read the workflow's environment into a `_RunConfig`."""
    return _RunConfig(
        repo=os.environ['REPO'],
        run_id=str(os.environ['RUN_ID']),
        workflow_name=os.environ['WORKFLOW_NAME'],
        run_url=os.environ['RUN_URL'],
        api_key=os.environ.get('OPENROUTER_API_KEY', ''),
        model=os.environ.get('OPENROUTER_MODEL') or DEFAULT_MODEL,
        notify_issue=int(os.environ['NOTIFY_ISSUE']) if os.environ.get('NOTIFY_ISSUE') else None,
        notify_origin=os.environ.get('NOTIFY_ORIGIN') or None,
    )


def _resolve_origin(config: _RunConfig) -> tuple[int | None, str | None, int | None]:
    """Locate the run's marker, degrading to "un-marked" if the lookup fails."""
    try:
        return github.resolve_origin(
            config.repo, config.run_id, config.notify_issue, config.notify_origin
        )
    except Exception as exc:  # search API rejection, rate limit, transient 5xx.
        # Nothing catches this above us: there is no workflow-level fallback
        # job any more, so an uncaught failure here loses the enrichment
        # outright rather than degrading through the paths below. When the
        # notifier told us its issue we can still carry on with that; without
        # it we continue as though the run were un-marked.
        summary.write_step_summary(
            f'Marker lookup failed ({exc}); treating this run as un-marked.'
        )
        return None, config.notify_origin, config.notify_issue


def _comment_on_rerun(config: _RunConfig, enriched_issue: int) -> None:
    """Rung zero: a re-run of the same failing jobs re-triggered us.

    Comment, don't skip and don't redo the full LLM pass. On a corpus of past
    scheduled failures this rung accounted for half the real duplicate pairs,
    making it the highest-value one.
    """
    github.gh(
        'issue',
        'comment',
        str(enriched_issue),
        '--repo',
        config.repo,
        '--body',
        f'Re-run attempt still failing: {config.run_url}\n\n'
        f'<!-- {MARKER_PREFIX}:run={config.run_id} -->',
    )
    summary.write_step_summary(
        f'Rung zero: run {config.run_id} already enriched on #{enriched_issue}; '
        'commented re-run note.'
    )


def _create_placeholder_issue(config: _RunConfig) -> tuple[int, str]:
    """Open a plain placeholder issue when no origin marker was found.

    Either a caller that has not been migrated to pass the issue through, or a
    marker lookup that failed. The first is the normal state of a repo part
    way through adopting this, so don't treat it as an anomaly -- just don't
    lose the notification.
    """
    summary.write_step_summary(
        'No notifier marker found for this run id; falling back to a plain issue.'
    )
    result = github.gh(
        'issue',
        'create',
        '--repo',
        config.repo,
        '--title',
        f"Scheduled workflow '{config.workflow_name}' failed",
        '--body',
        plain_fallback_body(config.workflow_name, config.run_url)
        + f'\n\n<!-- {MARKER_PREFIX}:run={config.run_id}:origin=new -->',
    )
    origin_issue = int(result.stdout.strip().rstrip('/').rsplit('/', 1)[-1])
    return origin_issue, 'new'


def _build_run_signature(config: _RunConfig) -> RunSignature:
    """Fetch the run's failed jobs and metadata, and reduce them to a signature."""
    failed_jobs = github.fetch_failed_jobs(config.repo, config.run_id)
    jobs_sig = [
        build_job_signature(
            job.id,
            job.name,
            job.failed_step,
            github.fetch_job_log(config.repo, config.run_id, job.id),
        )
        for job in failed_jobs
    ]
    meta = github.fetch_run_meta(config.repo, config.run_id)
    return build_run_signature(
        config.run_id, config.workflow_name, config.run_url, meta.get('createdAt', ''), jobs_sig
    )


def _plain_fallback_entry(config: _RunConfig, origin_kind: str | None, origin_issue: int) -> Any:
    """Build the envelope-shaped entry `apply_entry` uses when there is no LLM output."""
    if origin_kind == 'comment':
        return {
            'action': 'comment',
            'body': plain_fallback_body(config.workflow_name, config.run_url),
            'target_issue': origin_issue,
        }
    return {
        'action': 'new',
        'body': plain_fallback_body(config.workflow_name, config.run_url),
        'title': f"Scheduled workflow '{config.workflow_name}' failed",
        'labels': [],
        'issue_type': None,
    }


def _apply_plain_fallback(
    config: _RunConfig, origin_kind: str | None, origin_issue: int, enriched_marker: str
) -> None:
    """Apply the plain fallback entry against `origin_issue`."""
    apply_entry(
        config.repo,
        _plain_fallback_entry(config, origin_kind, origin_issue),
        enriched_marker,
        config.workflow_name,
        default_target=origin_issue,
    )


def _search_candidates(config: _RunConfig, origin_kind: str | None, origin_issue: int) -> str:
    """Build the {{CANDIDATES_BLOCK}} for the prompt, degrading to "none" on search failure."""
    try:
        open_candidates, closed_candidates = github.search_candidates(
            config.repo, config.workflow_name
        )
    except Exception as exc:  # as above: degrade to "no candidates", don't crash.
        summary.write_step_summary(
            f'Candidate search failed ({exc}); proceeding with no candidates.'
        )
        open_candidates, closed_candidates = [], []
    if origin_kind == 'new':
        # The placeholder this run just created is not a candidate to dedupe
        # against. An issue the notifier *commented* on is a different matter:
        # it already existed, the coarse search matched it, and it is the most
        # likely duplicate -- dropping it left the model blind to the very
        # issue it should have been comparing against, so it answered "new"
        # and produced the duplicate this whole path exists to avoid.
        open_candidates = [c for c in open_candidates if c.number != origin_issue]
    return build_candidates_block(
        open_candidates, closed_candidates, datetime.datetime.now(datetime.timezone.utc)
    )


def _fetch_envelope(
    config: _RunConfig, origin_kind: str | None, origin_issue: int, signature: RunSignature
) -> Any:
    """Ask the LLM to triage the failure, returning `None` on any failure along the way."""
    candidates_block = _search_candidates(config, origin_kind, origin_issue)
    system_prompt, user_prompt = prompt.build_prompt(
        config.workflow_name, config.run_url, signature, candidates_block
    )

    try:
        envelope = openrouter.call_openrouter(
            system_prompt, user_prompt, config.model, config.api_key
        )
    except Exception as exc:  # network error, non-2xx, bad JSON, and so on.
        summary.write_step_summary(
            f'OpenRouter call failed ({exc}); using the plain fallback body.'
        )
        return None

    envelope, dropped_fields = normalise_envelope(envelope)
    if dropped_fields:
        summary.write_step_summary(
            'Ignored fields that do not apply to the chosen action: '
            + ', '.join(dropped_fields)
            + '.'
        )

    errors = validate_envelope(envelope)
    if errors:
        summary.write_step_summary(
            'LLM output failed schema validation:\n' + '\n'.join(f'- {e}' for e in errors)
        )
        return None

    return envelope


def _apply_envelope(
    config: _RunConfig,
    envelope: Any,
    origin_kind: str | None,
    origin_issue: int,
    enriched_marker: str,
) -> None:
    """Act on a validated LLM envelope: upgrade, comment, or open a new issue."""
    if envelope['action'] == 'new' and origin_kind == 'new':
        # Upgrade the placeholder in place rather than creating a duplicate.
        available = github.existing_labels(config.repo)
        labels = github.filter_labels(envelope.get('labels') or [], available)
        edit_args = [
            'issue',
            'edit',
            str(origin_issue),
            '--repo',
            config.repo,
            '--title',
            envelope['title'],
            '--body',
            render_body(envelope['body'], config.workflow_name, enriched_marker),
        ]
        for label in labels:
            edit_args += ['--add-label', label]
        github.gh(*edit_args)
    elif envelope['action'] == 'comment' and envelope.get('target_issue') == origin_issue:
        apply_entry(
            config.repo,
            envelope,
            enriched_marker,
            config.workflow_name,
            default_target=origin_issue,
        )
    elif envelope['action'] == 'comment':
        # LLM picked a different candidate than the notifier's coarse match.
        apply_entry(config.repo, envelope, enriched_marker, config.workflow_name)
        if origin_kind == 'comment':
            github.gh(
                'issue',
                'comment',
                str(origin_issue),
                '--repo',
                config.repo,
                '--body',
                f'This looks like a distinct issue -- see #{envelope["target_issue"]}.\n\n'
                f'{enriched_marker}',
            )
    else:
        # action == "new" but origin_kind == "comment": the coarse title
        # match landed on an unrelated older issue; this is genuinely new.
        apply_entry(config.repo, envelope, enriched_marker, config.workflow_name)
        github.gh(
            'issue',
            'comment',
            str(origin_issue),
            '--repo',
            config.repo,
            '--body',
            f'This looks like a distinct issue from this one -- opened separately.\n\n'
            f'{enriched_marker}',
        )

    for also_entry in envelope.get('also') or []:
        apply_entry(config.repo, also_entry, enriched_marker, config.workflow_name)


def main() -> int:
    """Entry point: locate the run's marker, enrich or fall back, apply, and exit."""
    config = _read_config()

    enriched_issue, origin_kind, origin_issue = _resolve_origin(config)

    if enriched_issue is not None:
        _comment_on_rerun(config, enriched_issue)
        return 0

    if origin_issue is None:
        origin_issue, origin_kind = _create_placeholder_issue(config)

    signature = _build_run_signature(config)
    enriched_marker = render_enriched_marker(config.run_id, signature)

    if not config.api_key:
        summary.write_step_summary(
            'No OPENROUTER_API_KEY configured -- using the plain fallback body.'
        )
        _apply_plain_fallback(config, origin_kind, origin_issue, enriched_marker)
        return 0

    envelope = _fetch_envelope(config, origin_kind, origin_issue, signature)
    if envelope is None:
        _apply_plain_fallback(config, origin_kind, origin_issue, enriched_marker)
        return 0

    _apply_envelope(config, envelope, origin_kind, origin_issue, enriched_marker)
    return 0


if __name__ == '__main__':
    sys.exit(main())
