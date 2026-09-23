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

"""SEC0045 events: per-repo dispositions follow a fork back to its upstream."""

from __future__ import annotations

import subprocess


def test_fork_of_jubilant_gets_upstream_disposition(run_check, tmp_path):
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(['git', 'init', '-q'], cwd=tmp_path, check=True)
    for name, url in (
        ('origin', 'https://github.com/no-such-owner-charm-tech-baseline/jubilant'),
        ('upstream', 'https://github.com/canonical/jubilant'),
    ):
        # ruff: ignore[start-process-with-partial-path]
        subprocess.run(['git', 'remote', 'add', name, url], cwd=tmp_path, check=True)
    r = run_check('sec0045-events', 'product', {})
    assert r['status'] == 'na'
    assert 'Out of scope' in r['summary']
