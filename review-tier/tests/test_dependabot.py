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


"""Dependabot metadata, from real commit messages on canonical/operator's PRs."""

from __future__ import annotations

import pytest
from conftest import dependabot_commit, fixture, make_pr

from charm_tech_code.review_tier._tiers import bump_is_major, decide, update_types


def test_grouped_update_types():
    assert update_types(fixture('dependabot-2864.txt')) == [
        ('astral-sh/setup-uv', 'minor'),
        ('actions/setup-python', 'minor'),
        ('tiobe/tics-github-action', 'minor'),
        ('github/codeql-action/upload-sarif', 'minor'),
    ]


def test_grouped_update_types_with_majors():
    assert update_types(fixture('dependabot-2790.txt')) == [
        ('actions/checkout', 'patch'),
        ('astral-sh/setup-uv', 'major'),
        ('tiobe/tics-github-action', 'major'),
        ('github/codeql-action/upload-sarif', 'minor'),
    ]


ZERO_MINOR = """chore: bump foo from 0.41.0 to 0.42.0

---
updated-dependencies:
- dependency-name: foo
  dependency-version: 0.42.0
  dependency-type: direct:production
  update-type: version-update:semver-minor
...
"""


def test_zero_minor_update_is_major():
    assert update_types(ZERO_MINOR) == [('foo', 'major')]
    assert update_types(fixture('dependabot-2816.txt')) == [('ruff', 'patch')]


def test_zero_minor_needs_two_either_way(config):
    """The metadata and the commit's subject line agree about a 0.x minor bump."""
    for message in (ZERO_MINOR, 'chore: bump foo from 0.41.0 to 0.42.0'):
        pr = make_pr(['uv.lock'], author='dependabot[bot]', commits=[dependabot_commit(message)])
        assert decide(pr, config).required == 2


def test_indirect_update_has_no_type():
    assert update_types(fixture('dependabot-2900.txt')) == [('opentelemetry-api', None)]


@pytest.mark.parametrize(
    ('line', 'major'),
    [
        ('chore: bump opentelemetry-api from 1.45.1 to 1.45.2 in /examples/k8s-5-observe', False),
        ('chore: bump certifi from 2025.10.5 to 2026.10.19', True),
        ('chore: bump ruff from 0.16.9 to 0.16.10', False),
        ('chore: bump foo from 0.41.0 to 0.42.0', True),
        ('chore: bump foo from v0 to v1', True),
        ('chore: bump actions/checkout from v6.0.2 to v7.0.0', True),
        ('chore: bump actions/checkout from v7.0.0 to v7.0.1', False),
        ('chore: update sphinxcontrib-mermaid requirement from ~=2.0 to ~=2.1', None),
        ('chore: bump the actions group with 4 updates', None),
    ],
)
def test_bump_is_major(line, major):
    assert bump_is_major(line) is major


# (fixture, qualifies, words in the reason)
CASES = [
    ('2864', True, 'every update (4)'),
    ('2816', True, 'every update (1)'),
    ('2790', False, 'astral-sh/setup-uv, tiobe'),
    ('2674', False, 'major'),
    ('2625', False, 'rich'),
    ('2900', True, 'commit messages'),
    ('2842', True, 'commit messages'),
    ('2839', False, 'major bump'),
]


@pytest.mark.parametrize(('number', 'ok', 'words'), CASES)
def test_real_dependabot_prs(config, number, ok, words):
    pr = make_pr(
        ['uv.lock'],
        author='dependabot[bot]',
        commits=[dependabot_commit(fixture(f'dependabot-{number}.txt'))],
    )
    decision = decide(pr, config)
    assert decision.required == (1 if ok else 2)
    assert decision.reason.startswith('Dependabot bumps: ')
    assert words in decision.reason


def test_unclassifiable_message_needs_two(config):
    message = 'chore: update sphinxcontrib-mermaid requirement from ~=2.0 to ~=2.1'
    pr = make_pr(
        ['docs/requirements.txt'],
        author='dependabot[bot]',
        commits=[dependabot_commit(message)],
    )
    assert decide(pr, config).required == 2


def test_version_only_in_message_body(config):
    """Dependabot's subject line can leave out the versions, but the body has them."""
    pr = make_pr(
        ['examples/k8s-5-observe/uv.lock'],
        author='dependabot[bot]',
        commits=[dependabot_commit(fixture('dependabot-2900.txt'))],
    )
    assert decide(pr, config).required == 1


@pytest.mark.parametrize(
    'commit',
    [
        dependabot_commit('fix: the lock', author='tonyandrewmeyer', committer='tonyandrewmeyer'),
        # An author email can be spoofed; GitHub's signature can't.
        dependabot_commit('fix: the lock', committer='tonyandrewmeyer'),
        dependabot_commit('fix: the lock', verified=False),
        dependabot_commit('fix: the lock', author=None),
    ],
)
def test_someone_else_pushed_a_commit(config, commit):
    pr = make_pr(
        ['uv.lock'],
        author='dependabot[bot]',
        commits=[dependabot_commit(fixture('dependabot-2816.txt')), commit],
    )
    decision = decide(pr, config)
    assert decision.required == 2
    assert 'no longer just a bump' in decision.reason


def test_no_commits(config):
    pr = make_pr(['uv.lock'], author='dependabot[bot]')
    assert decide(pr, config).required == 2
