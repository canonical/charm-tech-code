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

import datetime
import os
import sys

from charm_tech_code.ai_failure_notifier import apply as _apply
from charm_tech_code.ai_failure_notifier import candidates as _candidates
from charm_tech_code.ai_failure_notifier import envelope as _envelope
from charm_tech_code.ai_failure_notifier import github as _github
from charm_tech_code.ai_failure_notifier import markers as _markers
from charm_tech_code.ai_failure_notifier import openrouter as _openrouter
from charm_tech_code.ai_failure_notifier import prompt as _prompt
from charm_tech_code.ai_failure_notifier import signatures as _signatures
from charm_tech_code.ai_failure_notifier import summary as _summary
from charm_tech_code.ai_failure_notifier.constants import DEFAULT_MODEL, MARKER_PREFIX


def main() -> int:
    """Entry point: locate the run's marker, enrich or fall back, apply, and exit."""
    repo = os.environ['REPO']
    run_id = str(os.environ['RUN_ID'])
    workflow_name = os.environ['WORKFLOW_NAME']
    run_url = os.environ['RUN_URL']
    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    model = os.environ.get('OPENROUTER_MODEL') or DEFAULT_MODEL
    # What the notifier did, when it tells us. Both are optional: an
    # unmigrated caller, or a notifier that failed before it got as far as an
    # issue, leaves them empty and we go looking instead.
    notify_issue = int(os.environ['NOTIFY_ISSUE']) if os.environ.get('NOTIFY_ISSUE') else None
    notify_origin = os.environ.get('NOTIFY_ORIGIN') or None

    try:
        enriched_issue, origin_kind, origin_issue = _github.resolve_origin(
            repo, run_id, notify_issue, notify_origin
        )
    except Exception as exc:  # search API rejection, rate limit, transient 5xx.
        # Nothing catches this above us: there is no workflow-level fallback
        # job any more, so an uncaught failure here loses the enrichment
        # outright rather than degrading through the paths below. When the
        # notifier told us its issue we can still carry on with that; without
        # it we continue as though the run were un-marked.
        _summary.write_step_summary(
            f'Marker lookup failed ({exc}); treating this run as un-marked.'
        )
        enriched_issue, origin_kind, origin_issue = None, notify_origin, notify_issue

    if enriched_issue is not None:
        # Rung zero: this run id was already fully enriched once -- a re-run of
        # the same failing jobs re-triggered us. Comment, don't skip and don't
        # redo the full LLM pass. On a corpus of past scheduled failures this
        # rung accounted for half the real duplicate pairs, making it the
        # highest-value one.
        _github.gh(
            'issue',
            'comment',
            str(enriched_issue),
            '--repo',
            repo,
            '--body',
            f'Re-run attempt still failing: {run_url}\n\n<!-- {MARKER_PREFIX}:run={run_id} -->',
        )
        _summary.write_step_summary(
            f'Rung zero: run {run_id} already enriched on #{enriched_issue}; '
            'commented re-run note.'
        )
        return 0

    if origin_issue is None:
        # Either a caller that has not been migrated to pass the issue
        # through, or a marker lookup that failed. The first is the normal
        # state of a repo part way through adopting this, so don't treat it
        # as an anomaly -- just don't lose the notification.
        _summary.write_step_summary(
            'No notifier marker found for this run id; falling back to a plain issue.'
        )
        result = _github.gh(
            'issue',
            'create',
            '--repo',
            repo,
            '--title',
            f"Scheduled workflow '{workflow_name}' failed",
            '--body',
            _apply.plain_fallback_body(workflow_name, run_url)
            + f'\n\n<!-- {MARKER_PREFIX}:run={run_id}:origin=new -->',
        )
        origin_issue = int(result.stdout.strip().rstrip('/').rsplit('/', 1)[-1])
        origin_kind = 'new'

    failed_jobs = _github.fetch_failed_jobs(repo, run_id)
    jobs_sig = [
        _signatures.build_job_signature(
            job.id, job.name, job.failed_step, _github.fetch_job_log(repo, run_id, job.id)
        )
        for job in failed_jobs
    ]
    meta = _github.fetch_run_meta(repo, run_id)
    signature = _signatures.build_run_signature(
        run_id, workflow_name, run_url, meta.get('createdAt', ''), jobs_sig
    )
    enriched_marker = _markers.render_enriched_marker(run_id, signature)

    if not api_key:
        _summary.write_step_summary(
            'No OPENROUTER_API_KEY configured -- using the plain fallback body.'
        )
        _apply.apply_entry(
            repo,
            {
                'action': 'comment' if origin_kind == 'comment' else 'new',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'title': f"Scheduled workflow '{workflow_name}' failed",
                'labels': [],
                'issue_type': None,
            }
            if origin_kind != 'comment'
            else {
                'action': 'comment',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'target_issue': origin_issue,
            },
            enriched_marker,
            workflow_name,
            default_target=origin_issue,
        )
        return 0

    try:
        open_candidates, closed_candidates = _github.search_candidates(repo, workflow_name)
    except Exception as exc:  # as above: degrade to "no candidates", don't crash.
        _summary.write_step_summary(
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
    candidates_block = _candidates.build_candidates_block(
        open_candidates, closed_candidates, datetime.datetime.now(datetime.timezone.utc)
    )
    system_prompt, user_prompt = _prompt.build_prompt(
        workflow_name, run_url, signature, candidates_block
    )

    try:
        envelope = _openrouter.call_openrouter(system_prompt, user_prompt, model, api_key)
    except Exception as exc:  # network error, non-2xx, bad JSON, and so on.
        _summary.write_step_summary(
            f'OpenRouter call failed ({exc}); using the plain fallback body.'
        )
        _apply.apply_entry(
            repo,
            {
                'action': 'new',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'title': f"Scheduled workflow '{workflow_name}' failed",
                'labels': [],
                'issue_type': None,
            }
            if origin_kind != 'comment'
            else {
                'action': 'comment',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'target_issue': origin_issue,
            },
            enriched_marker,
            workflow_name,
            default_target=origin_issue,
        )
        return 0

    envelope, dropped_fields = _envelope.normalise_envelope(envelope)
    if dropped_fields:
        _summary.write_step_summary(
            'Ignored fields that do not apply to the chosen action: '
            + ', '.join(dropped_fields)
            + '.'
        )

    errors = _envelope.validate_envelope(envelope)
    if errors:
        _summary.write_step_summary(
            'LLM output failed schema validation:\n' + '\n'.join(f'- {e}' for e in errors)
        )
        _apply.apply_entry(
            repo,
            {
                'action': 'new',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'title': f"Scheduled workflow '{workflow_name}' failed",
                'labels': [],
                'issue_type': None,
            }
            if origin_kind != 'comment'
            else {
                'action': 'comment',
                'body': _apply.plain_fallback_body(workflow_name, run_url),
                'target_issue': origin_issue,
            },
            enriched_marker,
            workflow_name,
            default_target=origin_issue,
        )
        return 0

    if envelope['action'] == 'new' and origin_kind == 'new':
        # Upgrade the placeholder in place rather than creating a duplicate.
        available = _github.existing_labels(repo)
        labels = _github.filter_labels(envelope.get('labels') or [], available)
        edit_args = [
            'issue',
            'edit',
            str(origin_issue),
            '--repo',
            repo,
            '--title',
            envelope['title'],
            '--body',
            _apply.render_body(envelope['body'], workflow_name, enriched_marker),
        ]
        for label in labels:
            edit_args += ['--add-label', label]
        _github.gh(*edit_args)
    elif envelope['action'] == 'comment' and envelope.get('target_issue') == origin_issue:
        _apply.apply_entry(
            repo, envelope, enriched_marker, workflow_name, default_target=origin_issue
        )
    elif envelope['action'] == 'comment':
        # LLM picked a different candidate than the notifier's coarse match.
        _apply.apply_entry(repo, envelope, enriched_marker, workflow_name)
        if origin_kind == 'comment':
            _github.gh(
                'issue',
                'comment',
                str(origin_issue),
                '--repo',
                repo,
                '--body',
                f'This looks like a distinct issue -- see #{envelope["target_issue"]}.\n\n'
                f'{enriched_marker}',
            )
    else:
        # action == "new" but origin_kind == "comment": the coarse title
        # match landed on an unrelated older issue; this is genuinely new.
        _apply.apply_entry(repo, envelope, enriched_marker, workflow_name)
        _github.gh(
            'issue',
            'comment',
            str(origin_issue),
            '--repo',
            repo,
            '--body',
            f'This looks like a distinct issue from this one -- opened separately.\n\n'
            f'{enriched_marker}',
        )

    for also_entry in envelope.get('also') or []:
        _apply.apply_entry(repo, also_entry, enriched_marker, workflow_name)

    return 0


if __name__ == '__main__':
    sys.exit(main())
