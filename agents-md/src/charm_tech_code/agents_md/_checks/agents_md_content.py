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

"""Check: AGENTS.md content is trustworthy.

Staleness detection, in five parts. A stale line is worse than a missing one,
because agents trust the file over the repo, so this is the part of the scheme
that has to be cheap enough to run on every change. Everything except running
commands is static, and running them is opt-in:

1. Commands parse and their entry-point tool resolves in a dev environment.
2. Safe commands actually pass, with `--run`. A command is only run when it
   starts with an allowlisted tool and subcommand (`make lint`, `uv run
   pytest`, `go test`, ...), needs no shell (no `&&`, pipes, redirects or
   `$`), changes nothing, and needs nothing the dev environment may not
   have (Docker, LXD, juju, root, integration). Everything else is only
   parsed and reported verify-manually, with the reason named. Each command
   can take up to three minutes and they run one after another, so `--run`
   is the expensive part and doesn't belong in a per-change check.
3. Paths and symbols resolve: every referenced file exists (a bare name
   anywhere in the repo, a link without its #anchor, and never a ~/ or
   absolute path, which describe the reader's machine, or a placeholder or
   glob such as `lib/<owner>/` or `**/*.py`); every named gocheck test suite
   (`-check.f <Suite>` after a `go test <package>`) still lives in the named
   package; every "`Symbol` in `path`" reference inside the repo resolves.
4. Version pins mentioned in prose (`tool@vX.Y.Z`) match what
   .github/workflows actually pin.
5. Scope lint: flag harness output that has leaked into AGENTS.md
   (attribution trailers and markers). Mentioning a harness by name, or its
   config directory, is often exactly what an AGENTS.md should do, so those
   are not findings.

This is a content check, not a presence check — see agents-md.py for
presence/length. If AGENTS.md is absent this check is n/a.

One check emits exactly one JSON result (see _common.emit_check), so all five
sub-checks fold into a single pass/fail carrying per-sub-check evidence.
"""

from __future__ import annotations

import glob
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

from .. import _common

CHECK_ID = 'agents-md-content'

RUNNABLE_TIMEOUT_SECONDS = 180

FENCE_RE = re.compile(r'```[ \t]*([A-Za-z0-9_+-]*)\n(.*?)\n?```', re.DOTALL)
FENCE_LANGS = {'', 'bash', 'sh', 'shell', 'console', 'zsh'}
# A `console` block is a transcript: commands carry a `$ ` prompt and every
# other line is output. Other shell blocks may have the prompt too.
PROMPT_RE = re.compile(r'^\$\s+')
TABLE_ROW_RE = re.compile(r'^\|(.+)\|[ \t]*$')
INLINE_CODE_RE = re.compile(r'`([^`\n]+)`')
COMMAND_ENTRYPOINTS = {
    'go',
    'tox',
    'make',
    'uv',
    'pytest',
    'docker',
    'npm',
    'cargo',
    'python',
    'python3',
    'pip',
    'sudo',
    'gofmt',
    'staticcheck',
    'govulncheck',
    'ruff',
    'black',
    'flake8',
    'pyright',
    'ty',
    'mypy',
    'just',
}
ENV_ASSIGN_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')

# Check 2 classification. Order matters: shell syntax first (a command run
# without a shell would get `&&` or `>` as an argument), then side effects,
# then environment-gate keywords, then the allowlist. Anything matching none
# of these is not run.
SHELL_SYNTAX_RE = re.compile(r'[|&;<>`$]')
SIDE_EFFECT_RE = re.compile(
    r'\bgo run\b|\bgo install\b|\bgo fmt\b(?!.*-l)|\bpip install\b'
    r'|\buv tool install\b|\buv pip install\b|(?:tox -e|make)\s+format\b'
    r'|\bruff format\b(?!.*(--check|--diff))|\bblack\b(?!.*--check)'
    r'|\bmake\s+run\b|\bmake\s+cli-help\b|\bnpm install\b|--fix\b|--write\b'
)
ENV_GATE_PATTERNS = [
    (re.compile(r'\bdocker\b|\bcompose\b', re.IGNORECASE), 'Docker'),
    (re.compile(r'\blxd\b', re.IGNORECASE), 'LXD'),
    (re.compile(r'\bjuju\b', re.IGNORECASE), 'juju'),
    (re.compile(r'\bcharmcraft\b', re.IGNORECASE), 'charmcraft'),
    (re.compile(r'\bsudo\b|\broot\b', re.IGNORECASE), 'root/sudo'),
    (re.compile(r'\bintegration\b', re.IGNORECASE), 'integration environment'),
    (re.compile(r'CHARM_PATH|packed charms?', re.IGNORECASE), 'packed charms'),
]
# The commands that are run with --run, as the leading words of the command
# once any `VAR=value` assignments and a `uv run [options]` wrapper are
# removed. A tool and subcommand, not a word anywhere in the line, so the
# default for anything unrecognised is not to run it.
RUNNABLE_COMMANDS = (
    ('make', 'lint'),
    ('make', 'test'),
    ('make', 'unit'),
    ('make', 'check'),
    ('tox', '-e', 'lint'),
    ('tox', '-e', 'static'),
    ('tox', '-e', 'unit'),
    ('pytest',),
    ('python', '-m', 'pytest'),
    ('python3', '-m', 'pytest'),
    ('ruff', 'check'),
    ('ruff', 'format', '--check'),
    ('ruff', 'format', '--diff'),
    ('pyright',),
    ('ty', 'check'),
    ('mypy',),
    ('go', 'test'),
    ('go', 'vet'),
    ('gofmt', '-l'),
    ('staticcheck',),
    ('govulncheck',),
    ('cargo', 'test'),
    ('cargo', 'check'),
    ('npm', 'test'),
)
# `uv run` options that take a value as the next word.
UV_RUN_VALUE_OPTIONS = frozenset({
    '--group',
    '--with',
    '--extra',
    '--python',
    '-p',
    '--package',
    '--directory',
    '--project',
    '--env-file',
})

VERSION_PIN_RE = re.compile(r'([A-Za-z0-9_.\-/]+)@v(\d+\.\d+(?:\.\d+)?)')
SUITE_RE = re.compile(r'go test\s+(\.[^\s]+)\s+.*-check\.f[= ]([A-Za-z_][A-Za-z0-9_]*)')
SYMBOL_IN_PATH_RE = re.compile(r'`([A-Za-z_][\w.]*)`\s+in\s+`([^`]+)`')
MD_LINK_RE = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
FILE_EXT_RE = re.compile(r'\.(md|py|go|toml|yaml|yml|txt|cfg|ini|sh|json|lock)$', re.IGNORECASE)
KNOWN_EXTENSIONLESS_FILENAMES = {'dockerfile', 'makefile', 'license', 'copying'}
# Characters that make a path a template (`lib/charms/<owner>/`,
# `{name}.yaml`) or a glob (`**/*.py`) rather than something to look up.
PLACEHOLDER_CHARS = frozenset('<>{}*?[]')
SKIPPED_DIRS = frozenset({
    '.git',
    '.venv',
    'venv',
    '.tox',
    'node_modules',
    '__pycache__',
    'build',
    'dist',
})

# Only what a harness writes, not what a person writes about one: a
# repository that is worked on with Claude Code may well say so, and point
# at `.claude/`, and that is guidance rather than leaked output.
SCOPE_LINT_PATTERNS = [
    (re.compile(r'Co-Authored-By', re.IGNORECASE), 'attribution trailer (Co-Authored-By)'),
    (re.compile(r'Generated (with|by)\s*\[?Claude', re.IGNORECASE), 'Claude attribution line'),
    (re.compile(r'\U0001F916'), 'robot-emoji attribution marker'),
]


def extract_commands(text: str) -> list[tuple[str, str]]:
    """Return (raw_command, source) pairs for the commands in AGENTS.md.

    Commands come from fenced shell blocks and from markdown table cells that
    look like commands.
    """
    commands: list[tuple[str, str]] = []
    for m in FENCE_RE.finditer(text):
        lang = m.group(1).lower()
        if lang not in FENCE_LANGS:
            continue
        for line in m.group(2).splitlines():
            line = line.strip()
            prompt = PROMPT_RE.match(line)
            if lang == 'console' and not prompt:
                continue
            if prompt:
                line = line[prompt.end() :]
            if not line or line.startswith('#'):
                continue
            cmd = re.split(r'\s+#\s?', line, maxsplit=1)[0].strip()
            if cmd:
                commands.append((cmd, 'fenced'))
    for line in text.splitlines():
        row = TABLE_ROW_RE.match(line.strip())
        if not row:
            continue
        for cell in row.group(1).split('|'):
            cell = cell.strip()
            code_m = INLINE_CODE_RE.fullmatch(cell)
            if not code_m:
                continue
            candidate = code_m.group(1).strip()
            first_tok = candidate.split()[0] if candidate.split() else ''
            if first_tok in COMMAND_ENTRYPOINTS:
                commands.append((candidate, 'table'))
    return commands


def entry_point_tool(cmd: str) -> str:
    """Return the first non-assignment token of the whole command line.

    A tool introduced mid-line by an explicit install step (e.g. `go install X &&
    X ...`) is intentionally not checked here — it's expected to be absent
    until that install step runs.
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return ''
    for tok in tokens:
        if ENV_ASSIGN_RE.match(tok):
            continue
        return tok
    return ''


def split_assignments(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split leading `VAR=value` words off a command, as the shell would."""
    env: dict[str, str] = {}
    for index, token in enumerate(tokens):
        if not ENV_ASSIGN_RE.match(token):
            return env, tokens[index:]
        name, _, value = token.partition('=')
        env[name] = value
    return env, []


def without_uv_run(words: list[str]) -> list[str]:
    """Return the command a `uv run [options]` wrapper runs, or *words* unchanged."""
    if words[:2] != ['uv', 'run']:
        return words
    index = 2
    while index < len(words) and words[index].startswith('-'):
        index += 2 if words[index] in UV_RUN_VALUE_OPTIONS else 1
    return words[index:]


def classify_command(cmd: str) -> tuple[str, str]:
    """Return (bucket, reason). bucket is 'runnable' or 'environment-gated'."""
    if SHELL_SYNTAX_RE.search(cmd):
        return 'environment-gated', 'needs a shell'
    if SIDE_EFFECT_RE.search(cmd):
        return 'environment-gated', 'side effects'
    for pattern, name in ENV_GATE_PATTERNS:
        if pattern.search(cmd):
            return 'environment-gated', name
    try:
        _, words = split_assignments(shlex.split(cmd))
    except ValueError:
        return 'environment-gated', 'unparseable'
    words = without_uv_run(words)
    if any(tuple(words[: len(prefix)]) == prefix for prefix in RUNNABLE_COMMANDS):
        return 'runnable', ''
    return 'environment-gated', 'not allowlisted'


def looks_like_path(cand: str) -> bool:
    """Return whether an inline-code snippet looks like a reference to a local file."""
    if not cand or ' ' in cand or cand.startswith(('http://', 'https://')):
        return False
    if cand.startswith(('~', '/')):
        # A home-directory or absolute path is about the reader's machine (a
        # cache, a config file), not the repo, so there is nothing to resolve.
        return False
    if not PLACEHOLDER_CHARS.isdisjoint(cand):
        return False
    if '/' in cand:
        # Exclude Go/domain-style import paths (github.com/..., gopkg.in/...,
        # golang.org/..., honnef.co/...) — a dotted first segment that isn't
        # itself a relative-path marker ("." / "..") means "module path",
        # not "local file".
        first_seg = cand.split('/', 1)[0]
        return '.' not in first_seg or first_seg.startswith('.')
    if cand.startswith('.'):
        return True
    if FILE_EXT_RE.search(cand):
        return True
    return cand.lower() in KNOWN_EXTENSIONLESS_FILENAMES


def extract_referenced_paths(text: str) -> set[str]:
    """Return the local paths referenced by markdown links and inline code."""
    paths: set[str] = set()
    for m in MD_LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith(('http://', 'https://', '#', 'mailto:')):
            continue
        # CONTRIBUTING.md#pull-requests is a reference to CONTRIBUTING.md.
        target = target.split('#', 1)[0].split('?', 1)[0]
        # A leading / in a markdown link is the repository root on GitHub.
        target = target.lstrip('/')
        if target and PLACEHOLDER_CHARS.isdisjoint(target):
            paths.add(target)
    for m in INLINE_CODE_RE.finditer(text):
        cand = m.group(1).strip()
        if looks_like_path(cand):
            paths.add(cand)
    return paths


def path_resolves(root: pathlib.Path, ref: str) -> bool:
    """Return whether a referenced path exists in the repo.

    A reference with a directory in it has to exist as written, relative to
    the root. A bare name (`_ast.py`, `_pypi_attest/`) is how prose refers to
    a file whose directory the surrounding text already makes clear, so it
    resolves if a file of that name (or a directory, with a trailing slash)
    exists anywhere in the repo outside the usual tool and build directories.
    """
    if not inside(root, ref):
        return False
    if (root / ref).exists():
        return True
    name = ref.rstrip('/')
    if not name or '/' in name:
        return False
    want_dir = ref.endswith('/')
    for found in root.rglob(glob.escape(name)):
        if not SKIPPED_DIRS.isdisjoint(found.relative_to(root).parts[:-1]):
            continue
        if not want_dir or found.is_dir():
            return True
    return False


def inside(root: pathlib.Path, ref: str) -> bool:
    """Return whether *ref*, taken relative to *root*, stays inside it.

    `root / '/etc/passwd'` is `/etc/passwd`, and `../x` is outside too: the
    check never reads a file it was pointed at outside the repo.
    """
    resolved_root = root.resolve()
    return (resolved_root / ref).resolve().is_relative_to(resolved_root)


def workflow_texts(root: pathlib.Path) -> dict[str, str]:
    """Return the text of each readable workflow file, keyed by repo-relative path."""
    wf_dir = root / '.github' / 'workflows'
    out: dict[str, str] = {}
    if not wf_dir.is_dir():
        return out
    for p in sorted(list(wf_dir.glob('*.yml')) + list(wf_dir.glob('*.yaml'))):
        try:
            out[str(p.relative_to(root))] = p.read_text(errors='replace')
        except OSError:  # ruff: ignore[try-except-in-loop]
            continue
    return out


def check_version_drift(
    pins: list[tuple[str, str]], workflows: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Return (drifted, checked) for the version pins mentioned in AGENTS.md.

    checked includes every pin that could be cross-referenced against a
    workflow (pass or fail), for evidence transparency — e.g. a tool version
    pinned differently in an unrelated workflow is visible even when the
    AGENTS.md claim matches somewhere.
    """
    drifted: list[dict] = []
    checked: list[dict] = []
    for tool, doc_version in pins:
        found: set[str] = set()
        for text in workflows.values():
            for vm in re.finditer(re.escape(tool) + r'@v(\d+\.\d+(?:\.\d+)?)', text):
                found.add(f'v{vm.group(1)}')
        if not found:
            # Not a failure: plenty of tools in an AGENTS.md were never
            # pinned in CI. But it's in the evidence, because a pin CI used to
            # have and has since dropped looks exactly like this.
            checked.append({'tool': tool, 'doc_version': doc_version, 'ci_versions': []})
            continue
        entry = {'tool': tool, 'doc_version': doc_version, 'ci_versions': sorted(found)}
        checked.append(entry)
        if doc_version not in found:
            drifted.append(entry)
    return drifted, checked


def scope_lint(text: str) -> list[str]:
    """Return a label for each kind of harness-shaped content found in `text`."""
    return [label for pattern, label in SCOPE_LINT_PATTERNS if pattern.search(text)]


def main() -> int:
    """Run the content checks, emit the result, and return the exit code."""
    root = _common.cd_repo_root()

    p = pathlib.Path('AGENTS.md')
    if not p.is_file():
        _common.emit_check(
            CHECK_ID,
            'na',
            'No AGENTS.md to content-check (see agents-md check for presence).',
        )
        return _common.EXIT_NA

    text = p.read_text(errors='replace')

    # --- Checks 1 & 2: commands ---
    run_commands = '--run' in sys.argv[1:]
    commands = extract_commands(text)
    missing_tools: list[dict] = []
    seen_missing_tools: set[str] = set()
    runnable: list[str] = []
    runnable_results: list[dict] = []
    gated: list[dict] = []

    for cmd, _source in commands:
        tool = entry_point_tool(cmd)
        if tool and tool not in seen_missing_tools and shutil.which(tool) is None:
            seen_missing_tools.add(tool)
            missing_tools.append({'command': cmd, 'tool': tool})

        bucket, reason = classify_command(cmd)
        if bucket == 'environment-gated':
            gated.append({'command': cmd, 'gating_dependency': reason})
            continue
        runnable.append(cmd)
        if not run_commands:
            continue

        # classify_command has already refused anything that needs a shell,
        # so the words are the whole command.
        assignments, words = split_assignments(shlex.split(cmd))
        try:
            proc = _common.run(
                words,
                cwd=root,
                timeout=RUNNABLE_TIMEOUT_SECONDS,
                env={**os.environ, **assignments},
            )
        except subprocess.TimeoutExpired:
            runnable_results.append({'command': cmd, 'status': 'timeout'})
            continue
        except OSError as exc:
            runnable_results.append({'command': cmd, 'status': 'error', 'detail': str(exc)})
            continue
        runnable_results.append({
            'command': cmd,
            'status': 'pass' if proc.returncode == 0 else 'fail',
            'returncode': proc.returncode,
            'stderr_tail': proc.stderr[-500:] if proc.returncode != 0 else '',
        })

    failed_runnable = [r for r in runnable_results if r['status'] != 'pass']

    # --- Check 3: paths & symbols ---
    ref_paths = extract_referenced_paths(text)
    missing_paths = sorted(rp for rp in ref_paths if not path_resolves(root, rp))

    symbol_findings: list[dict] = []
    for sym, sym_path in SYMBOL_IN_PATH_RE.findall(text):
        if not inside(root, sym_path):
            symbol_findings.append({
                'symbol': sym,
                'path': sym_path,
                'problem': 'path is outside the repo',
            })
            continue
        target = root / sym_path
        if not target.is_file():
            symbol_findings.append({
                'symbol': sym,
                'path': sym_path,
                'problem': 'path does not exist',
            })
            continue
        body = target.read_text(errors='replace')
        if not re.search(rf'\b{re.escape(sym)}\b', body):
            symbol_findings.append({
                'symbol': sym,
                'path': sym_path,
                'problem': 'symbol not found in file',
            })

    suite_findings: list[dict] = []
    for pkg, suite in SUITE_RE.findall(text):
        pkg_dir = (root / pkg).resolve()
        if not inside(root, pkg) or not pkg_dir.is_dir():
            suite_findings.append({
                'suite': suite,
                'package': pkg,
                'problem': 'package directory does not exist',
            })
            continue
        found = False
        for go_file in pkg_dir.rglob('*.go'):
            try:
                if re.search(rf'\b{re.escape(suite)}\b', go_file.read_text(errors='replace')):
                    found = True
                    break
            except OSError:
                continue
        if not found:
            suite_findings.append({
                'suite': suite,
                'package': pkg,
                'problem': 'suite identifier not found anywhere in package',
            })

    # --- Check 4: version pins vs CI ---
    pins = [
        (path.rstrip('/').split('/')[-1], f'v{ver}') for path, ver in VERSION_PIN_RE.findall(text)
    ]
    workflows = workflow_texts(root)
    version_drift, version_checked = check_version_drift(pins, workflows)

    # --- Check 5: scope lint ---
    scope_findings = scope_lint(text)

    problems: list[str] = []
    if missing_tools:
        problems.append(f'{len(missing_tools)} command tool(s) not resolvable')
    if failed_runnable:
        problems.append(f'{len(failed_runnable)} runnable command(s) did not pass')
    if missing_paths:
        problems.append(f'{len(missing_paths)} referenced path(s) missing')
    if symbol_findings:
        problems.append(f'{len(symbol_findings)} referenced symbol(s) unresolved')
    if suite_findings:
        problems.append(f'{len(suite_findings)} named test suite(s) not found in package')
    if version_drift:
        problems.append(f'{len(version_drift)} version pin(s) drifted from CI')
    if scope_findings:
        problems.append(f'{len(scope_findings)} scope-lint finding(s) (harness-shaped content)')

    evidence = {
        'path': 'AGENTS.md',
        'commands_extracted': len(commands),
        'missing_tools': missing_tools,
        'runnable': runnable,
        'commands_run': run_commands,
        'runnable_checked': len(runnable_results),
        'runnable_failed': failed_runnable,
        'environment_gated': gated,
        'paths_checked': sorted(ref_paths),
        'missing_paths': missing_paths,
        'symbol_findings': symbol_findings,
        'suite_findings': suite_findings,
        'version_pins_checked': version_checked,
        'version_drift': version_drift,
        'scope_lint_findings': scope_findings,
    }

    if problems:
        _common.emit_check(
            CHECK_ID,
            'fail',
            'AGENTS.md content check: ' + '; '.join(problems) + '.',
            evidence,
            {
                'kind': 'judgement',
                'human_review': (
                    'Review the evidence fields for the failing sub-check(s) '
                    '(missing_tools / runnable_failed / missing_paths / '
                    'symbol_findings / suite_findings / version_drift / '
                    'scope_lint_findings) and update AGENTS.md or the '
                    'underlying repo to match.'
                ),
            },
        )
        return _common.EXIT_FAIL

    ran = (
        f'{len(runnable_results)} run'
        if run_commands
        else f'{len(runnable)} runnable but not run without --run'
    )
    _common.emit_check(
        CHECK_ID,
        'pass',
        f'AGENTS.md content verified: {len(commands)} command(s) parsed '
        f'({ran}, {len(gated)} environment-gated/'
        f'verify-manually), {len(ref_paths)} path(s) resolved, '
        f'{len(version_checked)} version pin(s) cross-checked against CI, '
        'no scope-lint findings.',
        evidence,
    )
    return _common.EXIT_PASS


if __name__ == '__main__':
    sys.exit(main())
