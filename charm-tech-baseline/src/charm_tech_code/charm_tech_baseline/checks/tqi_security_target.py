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

"""Check: TQI security target — informational only.

Tier coverage: product only.

The TQI target lives in the central *TiCS Targets 26.10* spreadsheet,
not the repo. This check just emits an informational note prompting
the agent to verify the target is recorded for the cycle.
"""

from __future__ import annotations

import sys

from ..common import (
    EXIT_NA,
    EXIT_PASS,
    emit_check,
    parse_tier,
    tier_applies,
)

CHECK_ID = 'tqi-security-target'
APPLIES = 'product'


def main() -> int:
    """Emit the informational TQI security target note, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    emit_check(
        CHECK_ID,
        'unknown',
        (
            'Cannot verify from the repo — the TQI security target lives in the *TiCS Targets '
            '26.10* spreadsheet. Confirm a target is recorded for this product.'
        ),
        {},
        {
            'kind': 'judgement',
            'human_review': (
                'Set/verify the per-repo Security metric (TQI) target in *TiCS Targets 26.10* '
                'by 30 '
                'June.'
            ),
        },
    )
    return EXIT_PASS


if __name__ == '__main__':
    sys.exit(main())
