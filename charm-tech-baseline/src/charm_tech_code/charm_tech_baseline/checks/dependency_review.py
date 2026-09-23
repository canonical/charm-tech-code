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

"""Check: actions/dependency-review-action workflow present on PRs.

Tier coverage: product, canonical.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..common import (
    EXIT_FAIL,
    EXIT_NA,
    EXIT_PASS,
    cd_repo_root,
    emit_check,
    parse_tier,
    tier_applies,
)

CHECK_ID = 'dependency-review'
APPLIES = 'product,canonical'


def main() -> int:
    """Check dependency review runs on PRs, emit the result, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    cd_repo_root()

    wf_dir = Path('.github/workflows')
    if not wf_dir.is_dir():
        emit_check(
            CHECK_ID,
            'fail',
            'No .github/workflows/ directory.',
            {},
            {'kind': 'judgement', 'human_review': 'Set up workflows; then add dependency-review.'},
        )
        return EXIT_FAIL

    hit = ''
    for path in sorted(list(wf_dir.glob('*.yml')) + list(wf_dir.glob('*.yaml'))):
        try:
            if 'actions/dependency-review-action' in path.read_text(errors='replace'):
                hit = str(path)
                break
        except OSError:
            continue

    if hit:
        emit_check(
            CHECK_ID,
            'pass',
            'dependency-review-action wired up.',
            {'workflow': hit},
        )
        return EXIT_PASS

    emit_check(
        CHECK_ID,
        'fail',
        'No actions/dependency-review-action workflow.',
        {},
        {
            'kind': 'judgement',
            'human_review': (
                'Add a dependency-review.yaml workflow on pull_request, ~10 lines. Reference: '
                'canonical/operator#2587 (open as of 2026-06-27).'
            ),
        },
    )
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
