"""Umbrella check runner. Dispatches every check that applies to the resolved
tier and emits a single JSON report.

Usage:
    charm-tech-baseline check [--tier=product|canonical|personal]
                              [--only=<check>[,<check>...]]
                              [--format=json|markdown]
    charm-tech-baseline detect-tier
    charm-tech-baseline fix <fix-name> [args...]
    charm-tech-baseline list

Check IDs are the ones in the report (`code-of-conduct`, `security-md`, ...),
not module names.
"""

from __future__ import annotations

import datetime
import importlib
import pkgutil
import sys
from types import ModuleType

from . import checks as checks_pkg
from . import fixes as fixes_pkg
from . import tier as tier_mod
from .common import collecting, origin_url


def _modules(package: ModuleType) -> dict[str, ModuleType]:
    """Import every module in a subpackage, keyed by its declared ID.

    Checks carry a CHECK_ID; fixes have no such constant, so their module
    name with underscores turned back into hyphens is the name.
    """
    found: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f'{package.__name__}.{info.name}')
        found[getattr(module, 'CHECK_ID', info.name.replace('_', '-'))] = module
    return found


def usage() -> None:
    sys.stderr.write((__doc__ or '').strip() + '\n')


def _check(argv: list[str]) -> int:
    tier_override = ''
    only_filter = ''
    fmt = 'json'
    # Anything the runner does not recognise is passed through to the checks.
    # A check ignores flags it does not know, so this only means anything
    # alongside --only, where exactly one check is listening.
    passthrough: list[str] = []

    for arg in argv:
        if arg.startswith('--tier='):
            tier_override = arg[len('--tier=') :]
        elif arg.startswith('--only='):
            only_filter = arg[len('--only=') :]
        elif arg.startswith('--format='):
            fmt = arg[len('--format=') :]
        elif arg in ('-h', '--help'):
            print((__doc__ or '').strip())
            return 0
        elif arg.startswith('--'):
            passthrough.append(arg)
        else:
            print(f'Unknown argument: {arg}', file=sys.stderr)
            return 2

    if tier_override:
        tier = tier_override
        tier_source = 'override'
    else:
        tier = tier_mod.detect()
        tier_source = 'detected'

    if tier == 'unknown':
        print(
            'Could not detect tier; pass --tier=product|canonical|personal',
            file=sys.stderr,
        )
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
        # Each check reads its own flags off sys.argv, as it did when it was a
        # standalone script. Set it explicitly rather than letting the check
        # read the runner's own command line, so that a *detected* tier
        # reaches the check just as an overridden one does.
        sys.argv = [check_id, f'--tier={tier}', *passthrough]
        # A check that raises is a bug in the check, not a finding about the
        # repo, so it becomes a note rather than a fail.
        try:
            with collecting() as collected:
                module.main()
        except Exception as exc:  # noqa: BLE001
            notes.append(f'check {check_id} raised {type(exc).__name__}: {exc}')
            continue
        finally:
            sys.argv = saved_argv
        if not collected:
            notes.append(f'check {check_id} produced no result')
            continue
        results.extend(collected)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    repo = origin_url()

    if fmt == 'json':
        import json

        report = {
            'schema_version': 1,
            'repo': repo,
            'tier': tier,
            'tier_source': tier_source,
            'generated_at': generated_at,
            'checks': results,
            'notes': notes,
        }
        print(json.dumps(report))
        return 0

    # Markdown summary path — human spot-checks; agents should prefer JSON.
    print('# Repo-setup audit\n')
    print(f'- Repo: `{repo}`')
    print(f'- Tier: **{tier}** ({tier_source})')
    print(f'- Generated: {generated_at}\n')
    print('## Findings\n')
    for r in results:
        print(f'- **{r.get("status")}** (`{r.get("id")}`) — {r.get("summary")}')
    if notes:
        print('\n## Notes\n')
        for n in notes:
            print(f'- {n}')
    return 0


def _fix(argv: list[str]) -> int:
    if not argv:
        print('Usage: charm-tech-baseline fix <fix-name>', file=sys.stderr)
        return 2
    name, rest = argv[0], argv[1:]
    available = _modules(fixes_pkg)
    if name not in available:
        print(f'Unknown fix: {name}', file=sys.stderr)
        return 2
    # The fix scripts read sys.argv directly, as they did when each was its
    # own script.
    sys.argv = [f'charm-tech-baseline fix {name}', *rest]
    return available[name].main()


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
    if not argv or argv[0] in ('-h', '--help'):
        usage()
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    if command == 'check':
        return _check(rest)
    if command == 'detect-tier':
        sys.argv = ['detect-tier', *rest]
        return tier_mod.main()
    if command == 'fix':
        return _fix(rest)
    if command == 'list':
        return _list()
    print(f'Unknown command: {command}', file=sys.stderr)
    usage()
    return 2


if __name__ == '__main__':
    sys.exit(main())
