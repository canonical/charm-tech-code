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

"""Dependabot check: presence, ecosystems, and cooldown >= 7 days."""

from __future__ import annotations

import textwrap

PASSING = textwrap.dedent("""\
    version: 2
    updates:
      - package-ecosystem: pip
        directory: /
        schedule: {interval: weekly}
        cooldown:
          default-days: 7
      - package-ecosystem: github-actions
        directory: /
        schedule: {interval: weekly}
        cooldown:
          default-days: 7
    """)

SHORT_COOLDOWN = textwrap.dedent("""\
    version: 2
    updates:
      - package-ecosystem: pip
        directory: /
        schedule: {interval: weekly}
        cooldown:
          default-days: 3
    """)


def test_pass_when_ecosystems_have_cooldown(run_check):
    r = run_check('dependabot', 'canonical', {'.github/dependabot.yaml': PASSING})
    assert r['status'] == 'pass'
    assert r['evidence']['ecosystems'] == 2


def test_fail_when_cooldown_below_baseline(run_check):
    r = run_check('dependabot', 'canonical', {'.github/dependabot.yaml': SHORT_COOLDOWN})
    assert r['status'] == 'fail'
    assert 'cooldown' in r['summary'].lower()


def test_fail_when_config_missing(run_check):
    r = run_check('dependabot', 'canonical', {})
    assert r['status'] == 'fail'
