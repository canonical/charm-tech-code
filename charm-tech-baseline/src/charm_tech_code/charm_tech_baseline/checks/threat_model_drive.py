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

"""Check: Threat model — informational only.

Tier coverage: product only.

Threat models live in the central SSDLC Artifacts Drive. This check
emits an informational note prompting the agent to confirm the
Drive sheet is current for the cycle.
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

CHECK_ID = 'threat-model-drive'
APPLIES = 'product'


def main() -> int:
    """Emit the informational threat model note, and return the exit code."""
    tier = parse_tier()
    if not tier_applies(APPLIES, tier):
        emit_check(CHECK_ID, 'na', f'Not applicable for tier {tier}.')
        return EXIT_NA

    emit_check(
        CHECK_ID,
        'unknown',
        (
            'Cannot verify from the repo — threat models live in the SSDLC Artifacts Drive. '
            'Confirm '
            'a refreshed model exists for this cycle.'
        ),
        {},
        {
            'kind': 'judgement',
            'human_review': (
                'SEC0028: refresh every release cycle; demonstrate no unacceptable residual risk; '
                'any accepted risk needs a Risk Acceptance Form. Charm SDK consolidated sheet '
                'covers ops/ops-scenario/ops-tracing/jubilant/concierge; pebble has its own sheet.'
            ),
        },
    )
    return EXIT_PASS


if __name__ == '__main__':
    sys.exit(main())
