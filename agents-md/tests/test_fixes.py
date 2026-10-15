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

"""The add-agents-md fix, run the way an agent runs it."""

from __future__ import annotations

import subprocess


def _fix(cwd, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['agents-md', 'fix', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def test_copies_the_template(tmp_path):
    proc = _fix(tmp_path, 'add-agents-md')

    assert proc.returncode == 0, proc.stderr
    assert '{{REPO_DESCRIPTION_ONE_SENTENCE}}' in (tmp_path / 'AGENTS.md').read_text()


def test_copies_to_the_repo_root(tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    (tmp_path / 'sub').mkdir()

    proc = _fix(tmp_path / 'sub', 'add-agents-md')

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / 'AGENTS.md').exists()
    assert not (tmp_path / 'sub' / 'AGENTS.md').exists()


def test_refuses_to_overwrite(tmp_path):
    (tmp_path / 'AGENTS.md').write_text('# Ours\n')

    proc = _fix(tmp_path, 'add-agents-md')

    assert proc.returncode == 1
    assert (tmp_path / 'AGENTS.md').read_text() == '# Ours\n'
    assert 'refusing' in proc.stderr


def test_unknown_fix(tmp_path):
    proc = _fix(tmp_path, 'add-everything')

    assert proc.returncode == 2
    assert 'add-everything' in proc.stderr
