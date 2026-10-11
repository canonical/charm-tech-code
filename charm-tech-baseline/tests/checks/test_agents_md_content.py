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

"""AGENTS.md content check: the five Layer 1 staleness checks."""

from __future__ import annotations

import textwrap

CLEAN = textwrap.dedent("""\
    # AGENTS.md

    See [HACKING.md](HACKING.md) for details. Tests use `gopkg.in/check.v1`.

    ## Build and test

    ```bash
    true --check          # lint gate
    false --lxd deploy    # deploys via LXD, needs juju
    ```
    """)


def test_na_when_agents_md_missing(run_check):
    r = run_check('agents-md-content', 'canonical', {})
    assert r['status'] == 'na'


def test_pass_when_content_clean(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': CLEAN,
            'HACKING.md': '# Hacking\n',
        },
    )
    assert r['status'] == 'pass'
    assert r['evidence']['runnable_failed'] == []
    assert r['evidence']['missing_paths'] == []


def test_module_path_not_flagged_as_missing_file(run_check):
    # gopkg.in/check.v1 is a Go module path, not a local file — must not be
    # reported missing just because it contains a '/'.
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': CLEAN,
            'HACKING.md': '# Hacking\n',
        },
    )
    assert 'gopkg.in/check.v1' not in r['evidence']['missing_paths']


def test_environment_gated_command_not_executed(run_check):
    # `false` would fail if run; it must be classified environment-gated
    # (lxd/juju) and skipped, not executed — proven indirectly by the
    # overall check still passing (see test_pass_when_content_clean).
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': CLEAN,
            'HACKING.md': '# Hacking\n',
        },
    )
    gated_commands = [g['command'] for g in r['evidence']['environment_gated']]
    assert any(c.startswith('false') for c in gated_commands)
    assert not any(rr['command'].startswith('false') for rr in r['evidence']['runnable_failed'])


def test_fail_when_referenced_path_missing(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        See [BOGUS.md](BOGUS.md) for details.
        """)
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md})
    assert r['status'] == 'fail'
    assert 'BOGUS.md' in r['evidence']['missing_paths']


def test_fail_when_command_tool_missing(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        ```bash
        definitelynotarealbinary123 --check   # lint
        ```
        """)
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md})
    assert r['status'] == 'fail'
    assert any(m['tool'] == 'definitelynotarealbinary123' for m in r['evidence']['missing_tools'])


FAILING_TEST = 'def test_fails():\n    assert False\n'
PASSING_TEST = 'import os\n\n\ndef test_env():\n    assert os.environ["MARKER"] == "set"\n'


def _fenced(*commands: str, lang: str = 'bash') -> str:
    return '# AGENTS.md\n\n```' + lang + '\n' + '\n'.join(commands) + '\n```\n'


def test_commands_not_run_without_flag(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': _fenced('python3 -m pytest -q'), 'test_x.py': FAILING_TEST},
    )
    assert r['status'] == 'pass'
    assert r['evidence']['commands_run'] is False
    assert r['evidence']['runnable'] == ['python3 -m pytest -q']
    assert r['evidence']['runnable_checked'] == 0
    assert 'not run without --run' in r['summary']


def test_fail_when_runnable_command_fails(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': _fenced('python3 -m pytest -q'), 'test_x.py': FAILING_TEST},
        args=('--run',),
    )
    assert r['status'] == 'fail'
    assert r['evidence']['runnable_failed'][0]['command'] == 'python3 -m pytest -q'


def test_assignments_reach_the_command(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': _fenced('MARKER=set python3 -m pytest -q'), 'test_x.py': PASSING_TEST},
        args=('--run',),
    )
    assert r['status'] == 'pass', r['evidence']['runnable_failed']
    assert r['evidence']['runnable_checked'] == 1


def test_shell_syntax_is_never_run(run_check, tmp_path):
    # Run without a shell, `&&` would be an argument to rm: this deleted
    # build/ and was reported as a pass.
    (tmp_path / 'build').mkdir()
    (tmp_path / 'build' / 'keep').write_text('x')
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': _fenced('rm -rf build && make test', 'go test ./... > out.txt')},
        args=('--run',),
    )
    assert (tmp_path / 'build' / 'keep').exists()
    assert r['evidence']['runnable'] == []
    assert {g['gating_dependency'] for g in r['evidence']['environment_gated']} == {
        'needs a shell'
    }


def test_only_allowlisted_commands_are_runnable(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': _fenced(
                'uv run --group unit pytest tests/',
                'tox -e lint',
                'ruff check --fix .',
                'make all',
                'echo test',
            )
        },
    )
    assert r['evidence']['runnable'] == ['uv run --group unit pytest tests/', 'tox -e lint']
    reasons = {g['command']: g['gating_dependency'] for g in r['evidence']['environment_gated']}
    assert reasons == {
        'ruff check --fix .': 'side effects',
        'make all': 'not allowlisted',
        'echo test': 'not allowlisted',
    }


def test_console_block_is_a_transcript(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': _fenced('$ make lint', 'All checks passed!', lang='console')},
    )
    assert r['evidence']['commands_extracted'] == 1
    assert r['evidence']['runnable'] == ['make lint']
    assert all(m['tool'] != '$' for m in r['evidence']['missing_tools'])


def test_suite_not_found_in_package_flags_finding(run_check):
    # The canonical case: a gocheck suite documented against a package that
    # no longer contains it (pebble's PebbleSuite/cmd-pebble staleness).
    md = textwrap.dedent("""\
        # AGENTS.md

        ```bash
        go test ./internals/cli -check.f MySuite   # single suite
        ```
        """)
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': md,
            'internals/cli/other_test.go': 'package cli\n\nfunc TestSomethingElse() {}\n',
        },
    )
    findings = r['evidence']['suite_findings']
    assert any(
        f['suite'] == 'MySuite'
        and f['problem'] == 'suite identifier not found anywhere in package'
        for f in findings
    )


def test_suite_found_in_package_no_finding(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        ```bash
        go test ./internals/cli -check.f MySuite   # single suite
        ```
        """)
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': md,
            'internals/cli/suite_test.go': 'package cli\n\ntype MySuite struct{}\n',
        },
    )
    assert r['evidence']['suite_findings'] == []


def test_scope_lint_flags_harness_content(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        Some guidance for agents.

        Co-Authored-By: Claude <noreply@example.invalid>
        """)
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md})
    assert r['status'] == 'fail'
    assert r['evidence']['scope_lint_findings']


def test_placeholders_and_globs_are_not_paths(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        Libraries live in `lib/charms/<owner>/vN/<lib>.py`, one per
        `roadmap/{cycle}/` folder, and `**/*.py` is linted. Skills are in
        `~/.claude/skills/` and scratch goes in `/tmp/`. See
        [the guide](CONTRIBUTING.md#pull-requests) and [the root](/README.md).
        """)
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': md, 'CONTRIBUTING.md': '# x\n', 'README.md': '# x\n'},
    )
    assert r['evidence']['missing_paths'] == []
    assert r['status'] == 'pass'


def test_symbol_outside_the_repo_is_not_read(run_check):
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': '# AGENTS.md\n\nUsers are `root` in `/etc/passwd`.\n'},
    )
    assert r['status'] == 'fail'
    assert r['evidence']['symbol_findings'] == [
        {'symbol': 'root', 'path': '/etc/passwd', 'problem': 'path is outside the repo'}
    ]


def test_scope_lint_allows_naming_the_harness(run_check):
    md = textwrap.dedent("""\
        # AGENTS.md

        This repo is worked on with Claude Code and GitHub Copilot; the
        skills in `.claude/skills/` are symlinked into place.
        """)
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md, '.claude/skills/x': ''})
    assert r['evidence']['scope_lint_findings'] == []


def test_version_pin_drift_flagged(run_check):
    md = '# AGENTS.md\n\nPinned tool: widget/cmd/widget@v1.0.0 (see CI).\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': md,
            '.github/workflows/lint.yaml': (
                'steps:\n  - run: go install widget/cmd/widget@v2.0.0\n'
            ),
        },
    )
    assert r['status'] == 'fail'
    assert r['evidence']['version_drift']
    assert r['evidence']['version_drift'][0]['tool'] == 'widget'
    assert r['evidence']['version_drift'][0]['doc_version'] == 'v1.0.0'
    assert r['evidence']['version_drift'][0]['ci_versions'] == ['v2.0.0']


def test_version_pin_matches_ci(run_check):
    md = '# AGENTS.md\n\nPinned tool: widget/cmd/widget@v1.0.0 (see CI).\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': md,
            '.github/workflows/lint.yaml': (
                'steps:\n  - run: go install widget/cmd/widget@v1.0.0\n'
            ),
        },
    )
    assert r['status'] == 'pass'
    assert r['evidence']['version_drift'] == []
    assert r['evidence']['version_pins_checked'][0]['tool'] == 'widget'


def test_link_anchor_is_not_part_of_the_path(run_check):
    md = '# AGENTS.md\n\nSee [CONTRIBUTING.md](CONTRIBUTING.md#pull-requests).\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': md, 'CONTRIBUTING.md': '# Contributing\n\n## Pull requests\n'},
    )
    assert r['evidence']['missing_paths'] == []


def test_home_directory_path_is_not_a_repo_path(run_check):
    md = '# AGENTS.md\n\nThe corpus lives in `~/.cache/hyrum/charms`.\n'
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md})
    assert r['evidence']['missing_paths'] == []
    assert '~/.cache/hyrum/charms' not in r['evidence']['paths_checked']


def test_bare_name_resolves_anywhere_in_the_repo(run_check):
    md = '# AGENTS.md\n\nShared walkers live in `_ast.py`; the helper is `_attest/`.\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {
            'AGENTS.md': md,
            'src/pkg/_ast.py': '',
            'src/pkg/_attest/__init__.py': '',
        },
    )
    assert r['evidence']['missing_paths'] == []


def test_bare_name_still_missing_when_nowhere_in_the_repo(run_check):
    md = '# AGENTS.md\n\nShared walkers live in `_gone.py`.\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': md, '.venv/lib/_gone.py': ''},
    )
    assert r['status'] == 'fail'
    assert r['evidence']['missing_paths'] == ['_gone.py']


def test_path_with_directory_must_exist_as_written(run_check):
    md = '# AGENTS.md\n\nSee `docs/_ast.py`.\n'
    r = run_check('agents-md-content', 'canonical', {'AGENTS.md': md, 'src/_ast.py': ''})
    assert r['evidence']['missing_paths'] == ['docs/_ast.py']


def test_version_pin_ci_no_longer_pins_is_evidence(run_check):
    md = '# AGENTS.md\n\nPinned tool: widget/cmd/widget@v1.0.0 (see CI).\n'
    r = run_check(
        'agents-md-content',
        'canonical',
        {'AGENTS.md': md, '.github/workflows/lint.yaml': 'steps:\n  - run: make lint\n'},
    )
    assert r['status'] == 'pass'
    assert r['evidence']['version_pins_checked'] == [
        {'tool': 'widget', 'doc_version': 'v1.0.0', 'ci_versions': []}
    ]
