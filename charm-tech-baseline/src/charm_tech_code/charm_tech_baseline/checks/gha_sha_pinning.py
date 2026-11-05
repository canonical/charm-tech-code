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

"""Check: every third-party GHA action is SHA-pinned.

No exceptions — `actions/*`, `github/*`, `pypa/*`, `canonical/*` all pin to a commit
SHA, same as any other third-party action (see references/decisions.md).

Tier coverage: product, canonical, personal.

Implementation: greps `uses:` lines under .github/workflows/. A ref is
SHA-pinned iff it matches a 40-char hex string. Local action refs
(`./...`) are skipped.
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

CHECK_ID = 'gha-sha-pinning'
APPLIES = 'product,canonical,personal'

USES_RE = re.compile(r'^[ \t]*-?[ \t]*uses:[ \t]+(.+)$')
SHA_RE = re.compile(r'^[0-9a-fA-F]{40}$')


def main() -> int:
    """Check that every third-party action is SHA-pinned, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    cd_repo_root()

    wf_dir = Path('.github/workflows')
    if not wf_dir.is_dir():
        emit_check(CHECK_ID, 'na', 'No .github/workflows directory.')
        return EXIT_NA

    violations = 0
    violators: list[str] = []
    total = 0

    for p in sorted(list(wf_dir.glob('*.yml')) + list(wf_dir.glob('*.yaml'))):
        try:
            text = p.read_text(errors='replace')
        except OSError:
            continue
        for line in text.splitlines():
            m = USES_RE.match(line)
            if not m:
                continue
            ref = m.group(1).strip()
            # take first whitespace-delimited token, strip quotes
            ref = ref.split()[0] if ref else ''
            if ref.startswith('"') and ref.endswith('"'):
                ref = ref[1:-1]
            if ref.startswith("'") and ref.endswith("'"):
                ref = ref[1:-1]
            if not ref:
                continue
            if ref.startswith('./') or ref.startswith('.'):
                continue
            total += 1
            after_at = ref.split('@', 1)[1] if '@' in ref else ref
            if not SHA_RE.match(after_at):
                violations += 1
                violators.append(ref)

    if violations == 0:
        emit_check(
            CHECK_ID,
            'pass',
            'All third-party GHA actions SHA-pinned (no exceptions).',
            {'actions_inspected': total},
        )
        return EXIT_PASS

    trimmed = ','.join(violators)
    emit_check(
        CHECK_ID,
        'fail',
        f'{violations} third-party action ref(s) not SHA-pinned.',
        {'actions_inspected': total, 'non_pinned': trimmed},
        {
            'kind': 'judgement',
            'human_review': (
                'Replace each non-pinned ref with the upstream commit SHA + a # vX.Y.Z comment. '
                'No '
                'allowlist exceptions — actions/, github/, pypa/, canonical/ all pin the same way.'
            ),
        },
    )
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
