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


"""Builders for a PR and the operator configuration, shared by the tests."""

from __future__ import annotations

import pathlib

import pytest

from charm_tech_code.review_tier import _config
from charm_tech_code.review_tier._tiers import Commit, PullRequest

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def config() -> _config.Config:
    # A copy of canonical/operator's .github/review-tier.toml.
    return _config.parse(fixture('review-tier.toml'))


def make_pr(
    files=('test/test_main.py',),
    *,
    author='tonyandrewmeyer',
    branch='some-branch',
    lines=10,
    commits=(),
    labels=(),
    base=None,
    head=None,
) -> PullRequest:
    """A PR; `base` and `head` map paths to file text on each side."""
    sides = {'base': base or {}, 'head': head or {}}
    return PullRequest(
        author=author,
        branch=branch,
        lines_changed=lines,
        files=[f if isinstance(f, tuple) else (f, None) for f in files],
        commits=list(commits),
        labels_ever=set(labels),
        read=lambda path, side: sides[side].get(path),
    )


def dependabot_commit(message: str, **kw) -> Commit:
    args = dict(
        sha='0123456789abcdef', author='dependabot[bot]', committer='web-flow', verified=True
    )
    args.update(kw)
    return Commit(message=message, **args)
