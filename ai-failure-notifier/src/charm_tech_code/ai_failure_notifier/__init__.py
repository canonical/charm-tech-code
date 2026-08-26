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


"""Triage and enrich the issue opened when a scheduled workflow fails."""

from charm_tech_code.ai_failure_notifier.apply import (
    apply_entry,
    render_body,
)
from charm_tech_code.ai_failure_notifier.candidates import (
    build_candidates_block,
)
from charm_tech_code.ai_failure_notifier.cli import (
    main,
)
from charm_tech_code.ai_failure_notifier.constants import (
    MARKER_PREFIX,
)
from charm_tech_code.ai_failure_notifier.envelope import (
    ENVELOPE_JSON_SCHEMA,
    normalise_envelope,
    validate_envelope,
)
from charm_tech_code.ai_failure_notifier.github import (
    existing_labels,
    fetch_failed_jobs,
    fetch_job_log,
    locate_run_markers,
    resolve_origin,
    search_candidates,
    search_issue_numbers,
)
from charm_tech_code.ai_failure_notifier.markers import (
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
    'CandidateIssue',
    'ENVELOPE_JSON_SCHEMA',
    'FailedJob',
    'JobSignature',
    'MARKER_PREFIX',
    'PytestFailure',
    'RunSignature',
    'apply_entry',
    'build_candidates_block',
    'build_job_signature',
    'build_run_signature',
    'call_openrouter',
    'existing_labels',
    'fetch_failed_jobs',
    'fetch_job_log',
    'find_run_markers',
    'locate_run_markers',
    'main',
    'normalise_envelope',
    'parse_job_log',
    'render_body',
    'render_enriched_marker',
    'render_notifier_marker',
    'resolve_origin',
    'search_candidates',
    'search_issue_numbers',
    'signature_hash',
    'strip_line',
    'strip_log',
    'validate_envelope',
    'write_step_summary',
]
