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

"""Check: Conventional-commits PR-title enforcement workflow present.

Tier coverage: product, canonical.
"""

from __future__ import annotations

import re
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

CHECK_ID = 'conventional-commits'
APPLIES = 'product,canonical'

PATTERN = re.compile(
    r'amannn/action-semantic-pull-request|conventional-commit|check-conventional-pr-title'
)


def main() -> int:
    """Check PR titles are enforced, emit the result, and return the exit code."""
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
            'No .github/workflows directory.',
            {},
            {
                'kind': 'mechanical',
                'script': 'scripts/fixes/add-validate-pr-title.py',
                'human_review': (
                    'Installs operator-style validate-pr-title.yaml + '
                    'check-conventional-pr-title.py. Confirm CONTRIBUTING.md documents the '
                    'allowed '
                    'types.'
                ),
            },
        )
        return EXIT_FAIL

    hit = ''
    for path in sorted(list(wf_dir.glob('*.yml')) + list(wf_dir.glob('*.yaml'))):
        try:
            if PATTERN.search(path.read_text(errors='replace')):
                hit = str(path)
                break
        except OSError:
            continue

    if hit:
        emit_check(
            CHECK_ID,
            'pass',
            'PR-title Conventional-Commits enforcement wired up.',
            {'workflow': hit},
        )
        return EXIT_PASS

    emit_check(
        CHECK_ID,
        'fail',
        'No Conventional-Commits PR-title workflow found.',
        {},
        {
            'kind': 'mechanical',
            'script': 'scripts/fixes/add-validate-pr-title.py',
            'human_review': (
                'Installs operator-style validate-pr-title.yaml + check-conventional-pr-title.py '
                '(source: canonical/operator). Confirm CONTRIBUTING.md documents the allowed type '
                'list (chore/ci/docs/feat/fix/perf/refactor/revert/test) and disallows scopes.'
            ),
        },
    )
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
