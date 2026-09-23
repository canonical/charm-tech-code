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

"""Check: CODE_OF_CONDUCT.md present.

Tier coverage: product, canonical. (Best-practice for personal too;
emitted as a softer fail.)

Decision: link-only form pointing at the Ubuntu Code of Conduct, not a
full Contributor Covenant template. See references/decisions.md.
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

CHECK_ID = 'code-of-conduct'
APPLIES = 'product,canonical,personal'


def main() -> int:
    """Check CODE_OF_CONDUCT.md is present, emit the result, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    cd_repo_root()

    for path in ('CODE_OF_CONDUCT.md', 'docs/CODE_OF_CONDUCT.md', '.github/CODE_OF_CONDUCT.md'):
        p = Path(path)
        if p.is_file():
            text = p.read_text(errors='replace')
            if re.search(r'ubuntu\.com/community/ethos/code-of-conduct', text, re.IGNORECASE):
                emit_check(
                    CHECK_ID,
                    'pass',
                    'CODE_OF_CONDUCT.md present and links to the Ubuntu Code of Conduct.',
                    {'path': path},
                )
                return EXIT_PASS
            emit_check(
                CHECK_ID,
                'fail',
                (
                    'CODE_OF_CONDUCT.md present but does not link to the Ubuntu Code of Conduct '
                    '(cycle convention: link-only form).'
                ),
                {'path': path},
                {
                    'kind': 'judgement',
                    'human_review': (
                        'Replace with link-only form pointing at '
                        'https://ubuntu.com/community/ethos/code-of-conduct (Ubuntu CoC has its '
                        'own '
                        'reporting/enforcement path via Community Council).'
                    ),
                },
            )
            return EXIT_FAIL

    emit_check(
        CHECK_ID,
        'fail',
        'No CODE_OF_CONDUCT.md found.',
        {},
        {
            'kind': 'mechanical',
            'script': 'scripts/fixes/add-code-of-conduct.py',
            'human_review': 'None — template is fixed link-only form.',
        },
    )
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
