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


"""The console script and the REST client, with the network replaced."""

from __future__ import annotations

import json

import pytest
from conftest import fixture, make_pr

from charm_tech_code.review_tier import _cli, _github


@pytest.fixture
def summary(tmp_path, monkeypatch):
    path = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(path))
    monkeypatch.setenv('GITHUB_REPOSITORY', 'canonical/operator')
    return path


def run(monkeypatch, config, pr, approved):
    monkeypatch.setattr(_github, 'load', lambda gh, number: (pr, config, approved))
    return _cli.main(['2900'])


def test_small_change_with_one_approval(monkeypatch, config, summary, capsys):
    assert run(monkeypatch, config, make_pr(), ['dwilding']) == 0
    text = summary.read_text()
    assert 'Small change (Team PRs on low-risk paths), 1 approval needed' in text
    assert 'Current approvals: 1 (@dwilding)' in text
    assert '::error' not in capsys.readouterr().out


def test_two_approvals_needed(monkeypatch, config, summary, capsys):
    pr = make_pr(['ops/model.py'])
    assert run(monkeypatch, config, pr, ['dwilding']) == 1
    assert 'Not a small change, 2 approvals needed' in summary.read_text()
    out = capsys.readouterr().out
    assert '::error title=review-tier::1 of 2 approvals.' in out
    assert '`ops/model.py` is not on a low-risk path' in out


def test_no_approvals(monkeypatch, config, summary):
    assert run(monkeypatch, config, make_pr(), []) == 1
    assert 'nobody yet' in summary.read_text()


def test_paged_follows_links(monkeypatch):
    gh = _github.GitHub('canonical/operator', 'token')
    pages = {
        'https://api.github.com/repos/canonical/operator/x?per_page=100': (
            [1, 2],
            '<https://next.example/page2>; rel="next", <https://last>; rel="last"',
        ),
        'https://next.example/page2': ([3], ''),
    }
    monkeypatch.setattr(
        gh, '_open', lambda url, accept: (json.dumps(pages[url][0]).encode(), pages[url][1])
    )
    assert gh.paged('x') == [1, 2, 3]


def test_load(monkeypatch, config):
    """`load` reads the config from the base branch and the timeline's labels."""
    gh = _github.GitHub('o/r', None)
    pr = {
        'title': 't',
        'user': {'login': 'tonyandrewmeyer'},
        'labels': [{'name': 'docs'}],
        'base': {'ref': 'main', 'sha': 'b' * 40},
        'head': {'ref': 'x', 'sha': 'h' * 40},
        'additions': 3,
        'deletions': 4,
    }
    lists = {
        'issues/1/timeline': [
            {'event': 'labeled', 'label': {'name': 'full-review'}},
            {'event': 'unlabeled', 'label': {'name': 'full-review'}},
        ],
        'pulls/1/commits': [
            {
                'sha': 'c' * 40,
                'author': None,
                'committer': {'login': 'web-flow'},
                'commit': {'message': 'm'},
            }
        ],
        'pulls/1/files': [{'filename': 'test/a.py', 'previous_filename': 'ops/a.py'}],
        'pulls/1/reviews': [{'user': {'login': 'dwilding', 'type': 'User'}, 'state': 'APPROVED'}],
    }
    files = {}

    def file(path, ref):
        files[path] = ref
        return fixture('review-tier.toml')

    monkeypatch.setattr(gh, 'get', lambda path: {'pulls/1': pr}[path])
    monkeypatch.setattr(gh, 'paged', lambda path: lists[path])
    monkeypatch.setattr(gh, 'file', file)
    request, loaded, approved = _github.load(gh, 1)
    assert files == {'.github/review-tier.toml': 'main'}
    assert loaded == config
    assert approved == ['dwilding']
    assert request.labels_ever == {'docs', 'full-review'}
    assert request.lines_changed == 7
    assert request.files == [('test/a.py', 'ops/a.py')]
    assert request.commits[0].author is None
    assert not request.commits[0].verified
