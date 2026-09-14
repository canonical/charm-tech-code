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


"""The console script: a range of changes on stdin, one answer on stdout.

**This module is the package's I/O boundary, and the only one.** Everything
under it is text in, text out -- no network, no git, no filesystem, no clock
-- and the test suite's `no_clock` fixture holds that line by making a
`datetime` call from the library modules fail. This file is deliberately
outside that fixture, because `--date` has to default to something and
"today" is the only sensible default for a workflow that runs on the day it
releases. If you find yourself wanting the clock, or a file, or an API call,
in any other module of this package: it goes here instead.

Note what is *not* here: running `git log`. The log text arrives on stdin
exactly as the notes text does, so the boundary this module draws is around
the clock and the standard streams, and the caller keeps the subprocess.

The shape is driven by how a GitHub Actions step consumes a result, which is
either as a `$GITHUB_OUTPUT` line or as a file. A `$GITHUB_OUTPUT` line takes
a scalar comfortably and a multi-line document only through a heredoc
delimiter that the document itself must not contain -- so the two commands
that emit Markdown emit it on stdout, for the step to redirect into a file,
and the two that emit a scalar emit a single bare word with no decoration, so
that `size=$(changelog bump-size < log.txt)` is the whole of the plumbing::

    git log --reverse --no-merges --format="$(changelog git-log-format)" \\
        "$LAST_TAG..$BRANCH" > log.txt
    SIZE=$(changelog bump-size --team "$TEAM" < log.txt)
    VERSION=$(changelog next-version --previous "$LAST_TAG" --team "$TEAM" < log.txt)
    changelog release-notes --repo "$REPO" --team "$TEAM" < log.txt > release-notes.md
    changelog changes-entry --tag "$VERSION" --team "$TEAM" < log.txt > changes-entry.md

Five invocations re-parse the same text four times, which costs nothing and
buys each step an output that goes where it belongs without any reshaping.
`git-log-format` is the odd one out: it reads nothing and prints the
`--format` string the other four expect, so that the exact sequence of
`%x1e` and `%x1f` lives in one place rather than being copied into every
workflow that calls this.

`--input release-notes` switches the four back to GitHub's generated
release-notes text. That is the older path and the weaker one -- it reads
pull-request titles rather than commit subjects, and cannot resolve a revert
-- so it is the flag rather than the default.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Sequence

from ._constants import FULL_CHANGELOG_PREFIX, GIT_LOG_FORMAT
from ._format import format_changes, format_release_notes
from ._models import Change
from ._parse import parse_git_log, parse_release_notes
from ._version import infer_bump_size, next_version

#: The two things stdin may be. `git-log` is the default: see the module
#: docstring, and `_parse`.
GIT_LOG_INPUT = 'git-log'
RELEASE_NOTES_INPUT = 'release-notes'


def _today() -> datetime.date:
    """The default for `--date`, and the package's only reading of the clock.

    UTC rather than local time: the runner is UTC, and a release's date
    should not depend on who ran it from where.
    """
    return datetime.datetime.now(datetime.timezone.utc).date()


def _emit(text: str) -> None:
    """Write one answer to stdout, newline-terminated.

    The text is otherwise passed through exactly as the library produced it.
    `format_changes` output is prepended to a `CHANGES.md` verbatim, so the
    blank lines at its end are part of the answer rather than padding to be
    tidied up here.
    """
    sys.stdout.write(text if text.endswith('\n') else text + '\n')


def _input_options() -> argparse.ArgumentParser:
    """The options that say what is arriving on stdin.

    Shared by the four subcommands that read it, as a parent parser, so that
    a caller switching input path changes one flag on every command rather
    than learning four spellings of it.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        '--input',
        choices=(GIT_LOG_INPUT, RELEASE_NOTES_INPUT),
        default=GIT_LOG_INPUT,
        help=(
            "What is on stdin: a git log in this tool's format (the default, "
            "and the better source), or GitHub's generated release-notes text."
        ),
    )
    parser.add_argument(
        '--team',
        action='append',
        default=None,
        metavar='EMAIL-OR-HANDLE,...',
        help=(
            'Authors not to credit, comma-separated, as email addresses '
            'and/or GitHub handles. Repeatable. These are the people who '
            'maintain the repository; everyone else is credited by handle, '
            'or by name where no handle can be worked out. The default '
            'credits everyone.'
        ),
    )
    return parser


def _repo_option(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument(
        '--repo',
        required=required,
        metavar='OWNER/NAME',
        help=(
            'The repository the pull-request links point into. A change '
            'carries a number rather than a URL -- a number is all a git log '
            'has -- so the links are built from this.'
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='changelog',
        description=(
            'Turn a range of changes, read from stdin, into our changelog '
            'format or into a version decision.'
        ),
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    shared = [_input_options()]

    subparsers.add_parser(
        'bump-size',
        parents=shared,
        help="Print 'minor' or 'patch' for the changes on stdin.",
        description=(
            "Print 'minor' if the range contains a feature or a breaking change, "
            "and 'patch' otherwise. Never 'major': that is a deliberate act, not "
            'something to infer. On a branch where a feature should not appear at '
            'all, such as a maintenance branch, treat a "minor" here as an error '
            'rather than releasing from it.'
        ),
    )

    next_version_parser = subparsers.add_parser(
        'next-version',
        parents=shared,
        help='Print the version that follows --previous, given the changes on stdin.',
        description=(
            'Apply the inferred bump size to --previous and print the result. '
            'Only a plain X.Y.Z is accepted; whether the answer then gains a '
            'pre-release or dev suffix, and what it implies for any other '
            'package version in the repository, is for the caller to decide.'
        ),
    )
    next_version_parser.add_argument(
        '--previous',
        required=True,
        metavar='X.Y.Z',
        help='The version this release follows, normally the last tag on the branch.',
    )

    release_notes_parser = subparsers.add_parser(
        'release-notes',
        parents=shared,
        help='Print the release body, as Markdown.',
        description=(
            'Print the body of a GitHub release: the changes by category, '
            'breaking ones first, and a compare link at the end if there is '
            'one to print.'
        ),
    )
    _repo_option(release_notes_parser, required=True)
    release_notes_parser.add_argument(
        '--compare-url',
        default=None,
        metavar='URL',
        help=(
            'The compare link to end on. A git log has no equivalent of the '
            "line GitHub's generated notes end with, so on that path this is "
            'how to keep one; it overrides the line in the notes on the other. '
            'Omit it for no link at all.'
        ),
    )

    changes_entry_parser = subparsers.add_parser(
        'changes-entry',
        parents=shared,
        help='Print one CHANGES.md entry, as Markdown.',
        description=(
            'Print a single CHANGES.md entry for the release, to be prepended '
            'to the existing file.'
        ),
    )
    _repo_option(changes_entry_parser, required=False)
    changes_entry_parser.add_argument(
        '--tag',
        required=True,
        help='The version being released, used verbatim in the entry heading.',
    )
    changes_entry_parser.add_argument(
        '--date',
        type=datetime.date.fromisoformat,
        default=None,
        metavar='YYYY-MM-DD',
        help="The release date. Defaults to today's date, in UTC.",
    )

    subparsers.add_parser(
        'git-log-format',
        help='Print the git log --format string the other commands expect.',
        description=(
            'Print the --format string to pass to `git log`, and nothing else: '
            '`git log --format="$(changelog git-log-format)"`. Copying the '
            'string into a workflow instead would work until someone dropped a '
            'separator out of it, at which point the parse yields an empty '
            'changelog rather than an error, and a release goes out with '
            'nothing in its notes.'
        ),
    )

    return parser


def _team(args: argparse.Namespace) -> list[str]:
    """`--team a,b --team c` as one flat list.

    Both spellings, because a workflow passing a repository variable has one
    string with commas in it and a human typing the command has neither.
    """
    return [member for group in (args.team or ()) for member in group.split(',')]


def _categories(args: argparse.Namespace, text: str) -> tuple[dict[str, list[Change]], str | None]:
    """Parse stdin by whichever door `--input` names.

    The second half of the pair is the compare line, which only the notes
    path can produce for itself.
    """
    if args.input == RELEASE_NOTES_INPUT:
        return parse_release_notes(text, team=_team(args))
    repo = getattr(args, 'repo', None)
    return parse_git_log(text, team=_team(args), repo=repo), None


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the changes on stdin and print the answer the subcommand asks for."""
    args = _build_parser().parse_args(argv)

    if args.command == 'git-log-format':
        _emit(GIT_LOG_FORMAT)
        return 0

    categories, full_changelog = _categories(args, sys.stdin.read())

    if args.command == 'bump-size':
        _emit(infer_bump_size(categories))
    elif args.command == 'next-version':
        try:
            _emit(next_version(previous=args.previous, size=infer_bump_size(categories)))
        except ValueError as exc:
            print(f'changelog: {exc}', file=sys.stderr)
            return 2
    elif args.command == 'release-notes':
        if args.compare_url:
            full_changelog = f'{FULL_CHANGELOG_PREFIX}: {args.compare_url}'
        _emit(format_release_notes(categories, full_changelog, repo=args.repo))
    else:
        _emit(format_changes(categories, args.tag, args.date or _today()))

    return 0


if __name__ == '__main__':
    sys.exit(main())
