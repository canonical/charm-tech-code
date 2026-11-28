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


"""The console script: decide a PR's tier, count its approvals, pass or fail.

It reads `GITHUB_REPOSITORY` and `GITHUB_TOKEN` (or `GH_TOKEN`) from the
environment, takes the PR number as its argument, writes the decision to
`$GITHUB_STEP_SUMMARY` when there is one, and exits non-zero until the PR has
the approvals its tier needs.
"""

from __future__ import annotations

import argparse
import os

from . import _github
from ._tiers import decide


def report(tier: str | None, required: int, reason: str, approved: list[str]) -> str:
    """The Markdown the check shows: the tier, the rule that decided it, and who approved."""
    who = ', '.join(f'@{a}' for a in approved) or 'nobody yet'
    heading = f'Small change ({tier})' if tier else 'Not a small change'
    return (
        f'### review-tier: {heading}, {required} approval{"s" if required > 1 else ""} needed\n\n'
        f'{reason}\n\n'
        f'Current approvals: {len(approved)} ({who}).\n'
    )


def main(argv: list[str] | None = None) -> int:
    """Run the check against one PR."""
    parser = argparse.ArgumentParser(prog='review-tier', description=__doc__)
    parser.add_argument('pr', type=int, help='the pull request number')
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    args = parser.parse_args(argv)
    if not args.repo:
        parser.error('--repo or GITHUB_REPOSITORY is required')
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    pr, config, approved = _github.load(_github.GitHub(args.repo, token), args.pr)
    decision = decide(pr, config)
    text = report(decision.tier, decision.required, decision.reason, approved)
    print(text)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as f:
            f.write(text)
    if len(approved) >= decision.required:
        return 0
    # A workflow command, so the reason is on the PR's checks page as well as in the log.
    print(
        f'::error title=review-tier::{len(approved)} of {decision.required} approvals.'
        f' {decision.reason}'
    )
    return 1


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
