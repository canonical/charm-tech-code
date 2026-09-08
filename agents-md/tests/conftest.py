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

"""Shared helpers for the agents-md check tests.

The tests are functional: each writes a small tree into a tmp dir and runs
the real check through the installed console script, in a subprocess. No
mocking, and no importing the check into the test process, so a check that
reads the environment or shells out is exercised the way it really runs.
"""

from __future__ import annotations

import json
import subprocess

import pytest

CLI = 'agents-md'


@pytest.fixture
def run_check(tmp_path, monkeypatch):
    """Return ``run(check_name, files)`` -> parsed JSON dict.

    ``files`` is a mapping of repo-relative path -> file contents. Parent
    directories are created as needed. ``args`` are extra CLI flags passed
    after ``--only``. The check runs with cwd = tmp_path.
    """

    def _run(name: str, files: dict[str, str], args: tuple[str, ...] = ()) -> dict:
        for rel, body in files.items():
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        monkeypatch.chdir(tmp_path)
        proc = subprocess.run(
            [CLI, 'check', f'--only={name}', '--format=json', *args],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.stdout, f'{name} produced no stdout (stderr: {proc.stderr!r})'
        report = json.loads(proc.stdout)
        assert report['checks'], f'{name} produced no result (notes: {report["notes"]})'
        return report['checks'][0]

    return _run
