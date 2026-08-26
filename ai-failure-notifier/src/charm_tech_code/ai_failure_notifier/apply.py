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


"""Writing the decision back to GitHub, and the no-LLM fallback."""

from __future__ import annotations

from typing import Any

from charm_tech_code.ai_failure_notifier import github as _github
from charm_tech_code.ai_failure_notifier import summary as _summary


def plain_fallback_body(workflow_name: str, run_url: str) -> str:
    """The plain, generic body text used whenever enrichment is unavailable."""
    return f"Scheduled workflow '{workflow_name}' failed: {run_url}"


def render_body(body: str, workflow_name: str, marker: str) -> str:
    """Assemble an issue or comment body, footer and marker included.

    The `Workflow: <name>` footer is what keeps the notifier's coarse search
    working after enrichment has rewritten the title and body: the search
    matches on the workflow name, and without the footer it would depend on
    the model happening to leave the name in the title.
    """
    return f'{body.rstrip()}\n\nWorkflow: {workflow_name}\n\n{marker}'


def apply_entry(
    repo: str,
    entry: dict[str, Any],
    marker: str,
    workflow_name: str,
    *,
    default_target: int | None = None,
) -> str:
    """Create or comment on an issue per one envelope entry, stamping `marker`."""
    body = render_body(entry['body'], workflow_name, marker)
    if entry['action'] == 'new':
        # The repo's label set is centrally managed, so anything the model
        # asked for that doesn't exist is dropped rather than created.
        labels = _github.filter_labels(entry.get('labels') or [], _github.existing_labels(repo))
        dropped = set(entry.get('labels') or []) - set(labels)
        if dropped:
            _summary.write_step_summary(
                f'Dropped labels that do not exist in this repo: {", ".join(sorted(dropped))}.'
            )
        args = ['issue', 'create', '--repo', repo, '--title', entry['title'], '--body', body]
        for label in labels:
            args += ['--label', label]
        issue_type = entry.get('issue_type')
        result = None
        if issue_type:
            result = _github.gh(*args, '--type', issue_type, check=False)
            if result.returncode != 0:
                _summary.write_step_summary(
                    f'`gh issue create --type {issue_type}` failed ({result.stderr.strip()}); '
                    'retrying without --type.'
                )
                result = None
        if result is None:
            result = _github.gh(*args)
        return result.stdout.strip()
    else:
        target = entry.get('target_issue', default_target)
        _github.gh('issue', 'comment', str(target), '--repo', repo, '--body', body)
        return f'commented on #{target}'
