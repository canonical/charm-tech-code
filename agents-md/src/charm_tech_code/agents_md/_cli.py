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

"""Check runner. Dispatches every check and emits a single JSON report.

Usage:
    agents-md check [--only=<check>[,<check>...]]
                    [--format=json|markdown]
                    [--run] [--battery=<path>]
    agents-md fix <fix-name> [args...]
    agents-md list

Check IDs are the ones in the report (`agents-md`, `agents-md-content`,
`agents-md-battery`), not module names. `--run` makes agents-md-content run
the allowlisted commands it finds, which can take minutes; without it,
nothing in AGENTS.md is executed. `--battery` names the question battery for
agents-md-battery.

`check` exits 0 when every selected check ran, whatever it found: findings
are in the report, not the exit code. It exits 1 when a check raised or
produced no result (each is listed under `notes`), and 2 on a usage error.
"""

from __future__ import annotations

import datetime
import importlib
import json
import pkgutil
import sys
import types
from typing import TextIO

from . import _checks as checks_pkg
from . import _common
from . import _fixes as fixes_pkg

FORMATS = ('json', 'markdown')

# The flags a check reads off its own command line. Anything else is a typo,
# and a typo that silently does nothing looks like it worked.
CHECK_SWITCHES = ('--run',)
CHECK_OPTIONS = ('--battery=',)


def _modules(package: types.ModuleType) -> dict[str, types.ModuleType]:
    """Import every module in a subpackage, keyed by its declared ID.

    Checks carry a CHECK_ID; fixes have no such constant, so their module
    name with underscores turned back into hyphens is the name.
    """
    found: dict[str, types.ModuleType] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f'{package.__name__}.{info.name}')
        name = getattr(module, 'CHECK_ID', info.name.replace('_', '-'))
        if name in found:
            # Otherwise one of the two would silently never run.
            raise RuntimeError(f'{found[name].__name__} and {module.__name__} are both {name!r}')
        found[name] = module
    return found


def usage(stream: TextIO) -> None:
    """Write the usage text to *stream*."""
    stream.write((__doc__ or '').strip() + '\n')


def _check(argv: list[str]) -> int:
    only_filter = ''
    fmt = 'json'
    # Flags meant for a check are passed through to every selected check. A
    # check ignores flags it does not know.
    passthrough: list[str] = []

    for arg in argv:
        if arg.startswith('--only='):
            only_filter = arg[len('--only=') :]
        elif arg.startswith('--format='):
            fmt = arg[len('--format=') :]
        elif arg in ('-h', '--help'):
            usage(sys.stdout)
            return 0
        elif arg in CHECK_SWITCHES or arg.startswith(CHECK_OPTIONS):
            passthrough.append(arg)
        else:
            print(f'Unknown argument: {arg}', file=sys.stderr)
            return 2

    if fmt not in FORMATS:
        print(f'Unknown format: {fmt} (expected one of: {", ".join(FORMATS)})', file=sys.stderr)
        return 2

    available = _modules(checks_pkg)
    if only_filter:
        selected = {}
        for check_id in only_filter.split(','):
            if check_id not in available:
                print(f'Unknown check: {check_id}', file=sys.stderr)
                return 2
            selected[check_id] = available[check_id]
    else:
        selected = dict(sorted(available.items()))

    results: list[dict] = []
    notes: list[str] = []
    saved_argv = sys.argv
    for check_id, module in selected.items():
        # Each check reads its own flags off sys.argv. Set it explicitly
        # rather than letting the check read the runner's own command line.
        sys.argv = [check_id, *passthrough]
        # A check that raises is a bug in the check, not a finding about the
        # repo, so it becomes a note rather than a fail. SystemExit is caught
        # too, so that a check parsing its own arguments strictly can't take
        # the rest of the report down with it.
        try:
            with _common.collecting() as collected:
                module.main()
        except (Exception, SystemExit) as exc:
            notes.append(f'check {check_id} raised {type(exc).__name__}: {exc}')
            continue
        finally:
            sys.argv = saved_argv
        if not collected:
            notes.append(f'check {check_id} produced no result')
            continue
        results.extend(collected)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    repo = _common.origin_url()
    status = 1 if notes else 0

    if fmt == 'json':
        report = {
            'schema_version': 1,
            'repo': repo,
            'generated_at': generated_at,
            'checks': results,
            'notes': notes,
        }
        print(json.dumps(report))
        return status

    # Markdown summary path — human spot-checks; agents should prefer JSON.
    print('# AGENTS.md audit\n')
    print(f'- Repo: `{repo}`')
    print(f'- Generated: {generated_at}\n')
    print('## Findings\n')
    for r in results:
        print(f'- **{r.get("status")}** (`{r.get("id")}`) — {r.get("summary")}')
    if notes:
        print('\n## Notes\n')
        for n in notes:
            print(f'- {n}')
    return status


def _fix(argv: list[str]) -> int:
    if not argv:
        print('Usage: agents-md fix <fix-name>', file=sys.stderr)
        return 2
    name, rest = argv[0], argv[1:]
    available = _modules(fixes_pkg)
    if name not in available:
        print(f'Unknown fix: {name}', file=sys.stderr)
        return 2
    # The fixes read sys.argv directly.
    sys.argv = [f'agents-md fix {name}', *rest]
    try:
        return available[name].main()
    except _common.RepoRootUnreachableError as exc:
        print(exc, file=sys.stderr)
        return 3


def _list() -> int:
    print('checks:')
    for check_id in sorted(_modules(checks_pkg)):
        print(f'  {check_id}')
    print('fixes:')
    for name in sorted(_modules(fixes_pkg)):
        print(f'  {name}')
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        usage(sys.stderr)
        return 2
    if argv[0] in ('-h', '--help'):
        usage(sys.stdout)
        return 0
    command, rest = argv[0], argv[1:]
    if command == 'check':
        return _check(rest)
    if command == 'fix':
        return _fix(rest)
    if command == 'list':
        return _list()
    print(f'Unknown command: {command}', file=sys.stderr)
    usage(sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
