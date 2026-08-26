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


"""Triage and enrich the issue opened when a scheduled workflow fails.

Split into modules along the boundaries the single file already had. The
public names are re-exported here so that `from charm_tech_code import
ai_failure_notifier` keeps working as it did."""

from charm_tech_code.ai_failure_notifier.apply import (
    apply_entry,
    plain_fallback_body,
    render_body,
)
from charm_tech_code.ai_failure_notifier.candidates import (
    build_candidates_block,
    within_window,
)
from charm_tech_code.ai_failure_notifier.cli import (
    main,
)
from charm_tech_code.ai_failure_notifier.constants import (
    ANSI,
    CLOSED_CANDIDATE_WINDOW_DAYS,
    DEFAULT_MODEL,
    ERROR_MARKER,
    GO_FAIL,
    GROUP_END,
    GROUP_RUN_START,
    MARKER_PREFIX,
    MARKER_RE,
    MAX_CANDIDATES,
    PYTEST_SUMMARY,
    PYTEST_SUMMARY_END,
    RECENT_ISSUE_SCAN,
    TRACEBACK_END,
    TS,
)
from charm_tech_code.ai_failure_notifier.envelope import (
    ENVELOPE_JSON_SCHEMA,
    drop_inapplicable_fields,
    normalise_envelope,
    validate_entry,
    validate_envelope,
)
from charm_tech_code.ai_failure_notifier.github import (
    existing_labels,
    fetch_failed_jobs,
    fetch_issue_texts,
    fetch_job_log,
    fetch_run_meta,
    filter_labels,
    gh,
    gh_json,
    locate_run_markers,
    recent_issue_texts,
    resolve_origin,
    search_candidates,
    search_issue_numbers,
)
from charm_tech_code.ai_failure_notifier.markers import (
    Origin,
    find_run_markers,
    render_enriched_marker,
    render_notifier_marker,
    signature_hash,
)
from charm_tech_code.ai_failure_notifier.models import (
    CandidateIssue,
    FailedJob,
    JobSignature,
    PytestFailure,
    RunSignature,
)
from charm_tech_code.ai_failure_notifier.openrouter import (
    call_openrouter,
)
from charm_tech_code.ai_failure_notifier.prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    build_prompt,
)
from charm_tech_code.ai_failure_notifier.signatures import (
    build_job_signature,
    build_run_signature,
    parse_job_log,
    strip_line,
    strip_log,
)
from charm_tech_code.ai_failure_notifier.summary import (
    write_step_summary,
)

__all__ = [
    'ANSI',
    'CLOSED_CANDIDATE_WINDOW_DAYS',
    'CandidateIssue',
    'DEFAULT_MODEL',
    'ENVELOPE_JSON_SCHEMA',
    'ERROR_MARKER',
    'FailedJob',
    'GO_FAIL',
    'GROUP_END',
    'GROUP_RUN_START',
    'JobSignature',
    'MARKER_PREFIX',
    'MARKER_RE',
    'MAX_CANDIDATES',
    'Origin',
    'PYTEST_SUMMARY',
    'PYTEST_SUMMARY_END',
    'PytestFailure',
    'RECENT_ISSUE_SCAN',
    'RunSignature',
    'SYSTEM_PROMPT',
    'TRACEBACK_END',
    'TS',
    'USER_PROMPT_TEMPLATE',
    'apply_entry',
    'build_candidates_block',
    'build_job_signature',
    'build_prompt',
    'build_run_signature',
    'call_openrouter',
    'drop_inapplicable_fields',
    'existing_labels',
    'fetch_failed_jobs',
    'fetch_issue_texts',
    'fetch_job_log',
    'fetch_run_meta',
    'filter_labels',
    'find_run_markers',
    'gh',
    'gh_json',
    'locate_run_markers',
    'main',
    'normalise_envelope',
    'parse_job_log',
    'plain_fallback_body',
    'recent_issue_texts',
    'render_body',
    'render_enriched_marker',
    'render_notifier_marker',
    'resolve_origin',
    'search_candidates',
    'search_issue_numbers',
    'signature_hash',
    'strip_line',
    'strip_log',
    'validate_entry',
    'validate_envelope',
    'within_window',
    'write_step_summary',
]
