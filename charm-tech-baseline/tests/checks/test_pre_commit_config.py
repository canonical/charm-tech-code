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

"""pre-commit config: no tool versions in rev:, and no tag-pinned remote hooks."""

from __future__ import annotations

import textwrap

LOCAL_ONLY = textwrap.dedent("""\
    repos:
      - repo: local
        hooks:
          - id: check-yaml
            name: check yaml
            entry: uv run --group dev -- check-yaml
            language: system
            types: [yaml]
    """)


def _hygiene(rev: str) -> str:
    return textwrap.dedent(f"""\
        repos:
          - repo: https://github.com/pre-commit/pre-commit-hooks
            rev: {rev}
            hooks:
              - id: check-yaml
        """)


def test_pass_with_local_hooks_only(run_check):
    r = run_check('pre-commit-config', 'canonical', {'.pre-commit-config.yaml': LOCAL_ONLY})
    assert r['status'] == 'pass'


def test_pass_with_sha_pinned_hygiene_hooks(run_check):
    config = _hygiene('cef0300fd0fc4d2a87a85fa2093c6b283ea36f4b  # frozen: v5.0.0')
    r = run_check('pre-commit-config', 'canonical', {'.pre-commit-config.yaml': config})
    assert r['status'] == 'pass'


def test_tag_pinned_hygiene_hooks_point_at_language_system(run_check):
    r = run_check(
        'pre-commit-config', 'canonical', {'.pre-commit-config.yaml': _hygiene('v5.0.0')}
    )
    assert r['status'] == 'fail'
    assert r['evidence']['tag_pinned_revs'] == 1
    advice = r['remediation']['human_review']
    assert 'language: system' in advice
    assert 'frozen' in advice
    # The decision the advice cites has to be one decisions.md actually has.
    assert 'Tool pinning' in advice
    assert 'Remote pre-commit hooks' not in r['summary']
