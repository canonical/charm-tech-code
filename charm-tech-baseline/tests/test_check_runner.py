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

"""The runner: one smoke test that --only dispatches and shapes a report."""

from __future__ import annotations

import json
import subprocess


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
