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
import shutil
import subprocess
import sys

import pytest


def test_only_dispatches_selected_check(tmp_path):
    (tmp_path / '.github').mkdir()
    (tmp_path / '.github' / 'dependabot.yaml').write_text(
        'version: 2\nupdates:\n  - package-ecosystem: pip\n    directory: /\n'
        '    schedule: {interval: weekly}\n    cooldown: {default-days: 7}\n'
    )
    proc = subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', 'check', '--tier=canonical', '--only=dependabot'],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    report = json.loads(proc.stdout)
    assert report['tier'] == 'canonical'
    assert report['tier_source'] == 'override'
    assert [c['id'] for c in report['checks']] == ['dependabot']
    assert report['checks'][0]['status'] == 'pass'


def _listing() -> tuple[list[str], list[str]]:
    listing = subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', 'list'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    checks, fixes = listing.split('fixes:', 1)
    return checks.split()[1:], fixes.split()


def _run(tmp_path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


@pytest.mark.parametrize('tier', ['product', 'canonical', 'personal'])
def test_remediation_script_names_a_fix(tmp_path, tier):
    # A failing check's remediation.script is what an agent passes to
    # `charm-tech-baseline fix`, so it has to be one of the listed fix names.
    # An empty repo (plus one .yml, for the rename fix) fails most checks.
    (tmp_path / '.github' / 'workflows').mkdir(parents=True)
    (tmp_path / '.github' / 'workflows' / 'ci.yml').write_text('on: push\n')
    proc = _run(tmp_path, 'check', f'--tier={tier}')
    assert proc.returncode == 0, proc.stdout
    report = json.loads(proc.stdout)
    checks, fixes = _listing()
    assert report['notes'] == []
    assert sorted(c['id'] for c in report['checks']) == sorted(checks)
    scripts = {
        c['remediation']['script']
        for c in report['checks']
        if c['remediation'] and c['remediation'].get('script')
    }
    assert scripts
    assert scripts <= set(fixes)


def test_every_check_module_is_listed():
    # Two modules declaring the same CHECK_ID would hide one of them.
    from charm_tech_code.charm_tech_baseline import checks

    modules = [
        p for p in pathlib.Path(checks.__file__).parent.glob('*.py') if p.stem != '__init__'
    ]
    assert len(_listing()[0]) == len(modules)


def test_unknown_format_is_a_usage_error(tmp_path):
    proc = _run(tmp_path, 'check', '--tier=canonical', '--only=yaml-extension', '--format=jsonl')
    assert proc.returncode == 2
    assert proc.stdout == ''
    assert 'jsonl' in proc.stderr


def test_unknown_flag_is_a_usage_error(tmp_path):
    proc = _run(tmp_path, 'check', '--tier=canonical', '--only=yaml-extension', '--bogus')
    assert proc.returncode == 2
    assert proc.stdout == ''
    assert '--bogus' in proc.stderr


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


def test_report_names_the_baseline_repo(tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    for remote, owner in (('origin', 'someone'), ('upstream', 'canonical')):
        subprocess.run(
            # ruff: ignore[start-process-with-partial-path]
            ['git', 'remote', 'add', remote, f'https://github.com/{owner}/thing.git'],
            cwd=tmp_path,
            check=True,
        )
    # No gh on PATH, so the fork is found through the upstream remote.
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    (bin_dir / 'git').symlink_to(shutil.which('git') or 'git')
    env = {'PATH': f'{pathlib.Path(sys.executable).parent}:{bin_dir}', 'HOME': str(tmp_path)}
    proc = subprocess.run(
        # ruff: ignore[start-process-with-partial-path]
        ['charm-tech-baseline', 'check', '--tier=canonical', '--only=yaml-extension'],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=env,
    )
    report = json.loads(proc.stdout)
    assert report['repo'] == 'https://github.com/someone/thing'
    assert report['baseline_repo'] == 'canonical/thing'
