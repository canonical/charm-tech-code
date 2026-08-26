"""Shared helpers for the charm-tech-baseline check tests.

The tests are functional: each writes a small tree into a tmp dir and runs
the real check through the installed console script, in a subprocess. No
mocking, and no importing the check into the test process, so a check that
reads the environment or shells out is exercised the way it really runs.
"""

from __future__ import annotations

import json
import subprocess

import pytest

CLI = 'charm-tech-baseline'


@pytest.fixture
def run_check(tmp_path, monkeypatch):
    """Return ``run(check_name, tier, files)`` -> parsed JSON dict.

    ``files`` is a mapping of repo-relative path -> file contents. Parent
    directories are created as needed. ``args`` are extra CLI flags passed
    after ``--only``. The check runs with cwd = tmp_path.
    """

    def _run(name: str, tier: str, files: dict[str, str], args: tuple[str, ...] = ()) -> dict:
        for rel, body in files.items():
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        monkeypatch.chdir(tmp_path)
        proc = subprocess.run(
            [CLI, 'check', f'--tier={tier}', f'--only={name}', '--format=json', *args],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.stdout, f'{name} produced no stdout (stderr: {proc.stderr!r})'
        report = json.loads(proc.stdout)
        assert report['checks'], f'{name} produced no result (notes: {report["notes"]})'
        return report['checks'][0]

    return _run
