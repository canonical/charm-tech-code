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

"""detect-tier: override arg is pure; git-driven paths use a real init."""

from __future__ import annotations

import subprocess


def _run(*args, cwd=None):
    return subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', 'detect-tier', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def test_override_product():
    assert _run('product').stdout.strip() == 'product'


def test_override_rejects_garbage():
    proc = _run('something-else')
    assert proc.returncode != 0
    assert proc.stderr.strip() == 'unknown'


def test_canonical_product_repo_from_origin(tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['git', 'remote', 'add', 'origin', 'https://github.com/canonical/operator'],
        cwd=tmp_path,
        check=True,
    )
    assert _run(cwd=tmp_path).stdout.strip() == 'product'


def test_canonical_non_product_repo(tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['git', 'remote', 'add', 'origin', 'https://github.com/canonical/lxd'],
        cwd=tmp_path,
        check=True,
    )
    assert _run(cwd=tmp_path).stdout.strip() == 'canonical'


def test_fork_resolves_to_upstream_remote(tmp_path):
    # The origin owner does not exist, so the gh lookup finds nothing and the
    # `upstream` remote (in ssh form) is what identifies the canonical repo.
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    for name, url in (
        ('origin', 'git@github.com:no-such-owner-charm-tech-baseline/operator.git'),
        ('upstream', 'git@github.com:canonical/operator.git'),
    ):
        # ruff: ignore[start-process-with-partial-path]
        subprocess.run(['git', 'remote', 'add', name, url], cwd=tmp_path, check=True)
    assert _run(cwd=tmp_path).stdout.strip() == 'product'


def test_personal_repo_without_canonical_upstream(tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        [
            'git',
            'remote',
            'add',
            'origin',
            'https://github.com/no-such-owner-charm-tech-baseline/x',
        ],
        cwd=tmp_path,
        check=True,
    )
    assert _run(cwd=tmp_path).stdout.strip() == 'personal'
