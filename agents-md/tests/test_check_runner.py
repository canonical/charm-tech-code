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

"""The runner: dispatch, argument handling, and the shape of the report."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


def test_only_dispatches_selected_check(tmp_path):
    (tmp_path / 'AGENTS.md').write_text(
        '# AGENTS.md\n\nGuidance to AI agents working in this repo.\n\n'
        'Run the unit tests with `python -m pytest`.\n'
    )
    proc = subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['agents-md', 'check', '--only=agents-md'],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    report = json.loads(proc.stdout)
    assert [c['id'] for c in report['checks']] == ['agents-md']
    assert report['checks'][0]['status'] == 'pass'


def _run(tmp_path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['agents-md', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


def test_every_check_module_is_listed(tmp_path):
    # Two modules declaring the same CHECK_ID would hide one of them.
    from charm_tech_code.agents_md import _checks

    package = pathlib.Path(_checks.__file__).parent
    modules = [p for p in package.glob('*.py') if p.stem != '__init__']
    listing = _run(tmp_path, 'list').stdout
    assert len(listing.split('fixes:', 1)[0].split()[1:]) == len(modules)


def test_unknown_format_is_a_usage_error(tmp_path):
    proc = _run(tmp_path, 'check', '--only=agents-md', '--format=jsonl')
    assert proc.returncode == 2
    assert proc.stdout == ''
    assert 'jsonl' in proc.stderr


@pytest.mark.parametrize('flag', ['--bogus', '--runner', '--battery'])
def test_unknown_flag_is_a_usage_error(tmp_path, flag):
    proc = _run(tmp_path, 'check', '--only=agents-md', flag)
    assert proc.returncode == 2
    assert proc.stdout == ''
    assert flag in proc.stderr


def test_check_flags_are_accepted(tmp_path):
    proc = _run(tmp_path, 'check', '--only=agents-md', '--run', '--battery=x.yaml')
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize('args', [['-h'], ['check', '-h']])
def test_help_goes_to_stdout(tmp_path, args):
    proc = _run(tmp_path, *args)
    assert proc.returncode == 0
    assert 'Usage:' in proc.stdout
    assert proc.stderr == ''


def test_no_command_is_a_usage_error(tmp_path):
    proc = _run(tmp_path)
    assert proc.returncode == 2
    assert 'Usage:' in proc.stderr
