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


"""A small GitHub REST client, and the one place a PR is read from the network.

It uses the workflow's `GITHUB_TOKEN` and nothing else: no org-read token and no
secrets, so it works the same for a PR from a fork.
"""

from __future__ import annotations

import functools
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import _config
from ._tiers import Commit, PullRequest, approvers


class GitHub:
    """GET requests against one repository."""

    def __init__(self, repo: str, token: str | None):
        self.base = f'{os.environ.get("GITHUB_API_URL", "https://api.github.com")}/repos/{repo}'
        self.token = token

    def _open(self, url: str, accept: str) -> tuple[bytes, str]:
        headers = {'Accept': accept, 'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        request = urllib.request.Request(url, headers=headers)  # noqa: S310 (always https)
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read(), response.headers.get('Link', '')

    def get(self, path: str) -> Any:
        """One JSON response."""
        return json.loads(self._open(f'{self.base}/{path}', 'application/vnd.github+json')[0])

    def paged(self, path: str) -> list[Any]:
        """Every page of a list endpoint, following the `Link` header."""
        url: str | None = f'{self.base}/{path}{"&" if "?" in path else "?"}per_page=100'
        out: list[Any] = []
        while url:
            body, link = self._open(url, 'application/vnd.github+json')
            out += json.loads(body)
            m = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = m[1] if m else None
        return out

    def file(self, path: str, ref: str) -> str | None:
        """A file's text at a commit or branch, or None if it isn't there."""
        quoted = urllib.parse.quote(path)
        url = f'{self.base}/contents/{quoted}?ref={urllib.parse.quote(ref)}'
        try:
            return self._open(url, 'application/vnd.github.raw')[0].decode()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise


def load(gh: GitHub, number: int) -> tuple[PullRequest, _config.Config, list[str]]:
    """Read a PR, the configuration on its base branch, and who has approved it."""
    pr = gh.get(f'pulls/{number}')
    text = gh.file(_config.PATH, pr['base']['ref'])
    if text is None:
        raise SystemExit(f'No {_config.PATH} on the base branch {pr["base"]["ref"]}.')
    config = _config.parse(text)
    author = pr['user']['login']

    @functools.cache
    def merge_base() -> str:
        compare = gh.get(f'compare/{pr["base"]["sha"]}...{pr["head"]["sha"]}')
        return compare['merge_base_commit']['sha']

    def read(path: str, side: str) -> str | None:
        return gh.file(path, merge_base() if side == 'base' else pr['head']['sha'])

    labels = {label['name'] for label in pr['labels']}
    for event in gh.paged(f'issues/{number}/timeline'):
        if event.get('event') == 'labeled':
            labels.add(event['label']['name'])
    commits = [
        Commit(
            sha=c['sha'],
            author=(c.get('author') or {}).get('login'),
            committer=(c.get('committer') or {}).get('login'),
            verified=bool(c['commit'].get('verification', {}).get('verified')),
            message=c['commit']['message'],
        )
        for c in gh.paged(f'pulls/{number}/commits')
    ]
    files = [
        (f['filename'], f.get('previous_filename')) for f in gh.paged(f'pulls/{number}/files')
    ]
    # GitHub stops these lists at 250 commits and 3000 files, and a short list
    # could leave out the commit or file that rules out a tier. No tier is meant
    # for a PR that size, so it needs two approvals rather than a decision on
    # part of it.
    incomplete = None
    if len(commits) < pr['commits'] or len(files) < pr['changed_files']:
        incomplete = (
            f'GitHub lists only {len(commits)} of the {pr["commits"]} commits and'
            f' {len(files)} of the {pr["changed_files"]} files in this PR'
        )
    request = PullRequest(
        title=pr['title'],
        author=author,
        branch=pr['head']['ref'],
        lines_changed=pr['additions'] + pr['deletions'],
        files=files,
        commits=commits,
        labels_ever=labels,
        read=read,
        incomplete=incomplete,
    )
    reviews = gh.paged(f'pulls/{number}/reviews')
    return request, config, approvers(reviews, author, config.reviewers)
