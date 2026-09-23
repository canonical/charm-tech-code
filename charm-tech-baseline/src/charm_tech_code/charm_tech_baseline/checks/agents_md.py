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

"""Check: AGENTS.md present (best-of-class; agent-onboarding entry point).

Tier coverage: product, canonical. Personal-tier: informational only.

Convention: keep it minimal — a short pointer file, not an encyclopaedia.
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

CHECK_ID = 'agents-md'
APPLIES = 'product,canonical,personal'


def main() -> int:
    """Check AGENTS.md is present and minimal, emit the result, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    cd_repo_root()

    p = Path('AGENTS.md')
    if p.is_file():
        lines = p.read_text().count('\n')
        if lines > 200:
            emit_check(
                CHECK_ID,
                'fail',
                f"AGENTS.md present but at {lines} lines is well past the 'keep it minimal' "
                f'convention.',
                {'path': 'AGENTS.md', 'lines': lines},
                {
                    'kind': 'judgement',
                    'human_review': (
                        'Trim AGENTS.md down — point at HACKING/CONTRIBUTING for depth; keep '
                        'AGENTS.md to setup commands and conventions only.'
                    ),
                },
            )
            return EXIT_FAIL
        emit_check(
            CHECK_ID,
            'pass',
            f'AGENTS.md present ({lines} lines).',
            {'path': 'AGENTS.md', 'lines': lines},
        )
        return EXIT_PASS

    emit_check(
        CHECK_ID,
        'fail',
        'No AGENTS.md found.',
        {},
        {
            'kind': 'mechanical',
            'script': 'scripts/fixes/add-agents-md.py',
            'human_review': 'Customise the dev-setup commands for this repo (uv / go / make / '
            'just).',
        },
    )
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
