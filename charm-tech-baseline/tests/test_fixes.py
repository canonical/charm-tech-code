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

"""The fixes that move files or change GitHub, run the way an agent runs them."""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
import sys


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _fix(repo: pathlib.Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', 'fix', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo,
        env=env,
    )


def _repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    repo = tmp_path / 'repo'
    for rel, body in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body)
    repo.mkdir(exist_ok=True)
    _git(repo, 'init', '-q')
    return repo


class TestRenameYmlToYaml:
    def test_renames_tracked_and_untracked(self, tmp_path):
        repo = _repo(tmp_path, {'.github/workflows/ci.yml': 'on: push\n'})
        _git(repo, 'add', '.')
        (repo / '.github' / 'dependabot.yml').write_text('version: 2\n')

        proc = _fix(repo, 'rename-yml-to-yaml')

        assert proc.returncode == 0, proc.stderr
        assert sorted(p.name for p in (repo / '.github').rglob('*.y*ml')) == [
            'ci.yaml',
            'dependabot.yaml',
        ]
        # The tracked file was moved in the index too, so history follows it.
        tracked = subprocess.run(
            # ruff: ignore[start-process-with-partial-path]
            ['git', 'ls-files'],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert tracked == ['.github/workflows/ci.yaml']
        assert 'Done: 2 renamed, 0 skipped, 0 failed.' in proc.stdout

    def test_existing_twin_is_skipped(self, tmp_path):
        repo = _repo(
            tmp_path,
            {'.github/workflows/ci.yml': 'old\n', '.github/workflows/ci.yaml': 'new\n'},
        )

        proc = _fix(repo, 'rename-yml-to-yaml')

        assert proc.returncode == 0
        assert (repo / '.github' / 'workflows' / 'ci.yml').read_text() == 'old\n'
        assert 'SKIP' in proc.stderr

    def test_failed_git_mv_is_not_reported_as_renamed(self, tmp_path):
        repo = _repo(tmp_path, {'.github/workflows/ci.yml': 'on: push\n'})
        _git(repo, 'add', '.')
        # A held index lock makes git mv refuse, as it would mid-way through
        # another git command; git ls-files still works.
        (repo / '.git' / 'index.lock').touch()

        proc = _fix(repo, 'rename-yml-to-yaml')

        assert proc.returncode == 1
        assert (repo / '.github' / 'workflows' / 'ci.yml').exists()
        assert 'Renamed' not in proc.stdout
        assert 'FAILED: .github/workflows/ci.yml' in proc.stderr
        assert '0 renamed, 0 skipped, 1 failed' in proc.stdout


class TestApplyRepoSettings:
    def _env(self, tmp_path: pathlib.Path, gh_exit: int) -> dict[str, str]:
        """Put a fake gh on PATH that logs its arguments and exits *gh_exit*."""
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        gh = bin_dir / 'gh'
        gh.write_text(
            f'#!/bin/sh\necho "$@" >> {tmp_path / "gh.log"}\n'
            # Not a fork, as far as `gh repo view` is concerned.
            f'case "$1" in repo) exit 0;; esac\nexit {gh_exit}\n'
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        (bin_dir / 'git').symlink_to(shutil.which('git') or 'git')
        return {
            'PATH': f'{pathlib.Path(sys.executable).parent}:{bin_dir}',
            'HOME': str(tmp_path),
        }

    def _calls(self, tmp_path: pathlib.Path) -> list[str]:
        log = tmp_path / 'gh.log'
        return log.read_text().splitlines() if log.exists() else []

    def test_dry_run_calls_nothing(self, tmp_path):
        repo = _repo(tmp_path, {})
        _git(repo, 'remote', 'add', 'origin', 'https://github.com/canonical/thing.git')

        proc = _fix(repo, 'apply-repo-settings', '--dry-run', env=self._env(tmp_path, 0))

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.count('+ gh api') == 3
        assert 'repos/canonical/thing/actions/permissions' in proc.stdout
        assert self._calls(tmp_path) == []

    def test_personal_repo_keeps_its_actions_policy(self, tmp_path):
        repo = _repo(tmp_path, {})
        _git(repo, 'remote', 'add', 'origin', 'https://github.com/someone/thing.git')

        proc = _fix(repo, 'apply-repo-settings', '--dry-run', env=self._env(tmp_path, 0))

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.count('+ gh api') == 2
        assert 'actions/permissions' not in proc.stdout

    def test_fork_patches_upstream(self, tmp_path):
        repo = _repo(tmp_path, {})
        _git(repo, 'remote', 'add', 'origin', 'https://github.com/someone/thing.git')
        _git(repo, 'remote', 'add', 'upstream', 'https://github.com/canonical/thing.git')

        proc = _fix(repo, 'apply-repo-settings', '--dry-run', env=self._env(tmp_path, 0))

        assert proc.returncode == 0, proc.stderr
        assert 'repos/canonical/thing ' in proc.stdout
        assert 'someone' not in proc.stdout

    def test_failed_call_is_reported(self, tmp_path):
        repo = _repo(tmp_path, {})
        _git(repo, 'remote', 'add', 'origin', 'https://github.com/canonical/thing.git')

        proc = _fix(repo, 'apply-repo-settings', env=self._env(tmp_path, 1))

        assert proc.returncode == 1
        assert 'Done.' not in proc.stdout
        assert 'failed' in proc.stderr
        # Each setting is independent, so a failure doesn't stop the rest.
        assert sum(call.startswith('api') for call in self._calls(tmp_path)) == 3

    def test_unknown_argument(self, tmp_path):
        repo = _repo(tmp_path, {})

        proc = _fix(repo, 'apply-repo-settings', '--force', env=dict(os.environ))

        assert proc.returncode == 2
        assert '--force' in proc.stderr
