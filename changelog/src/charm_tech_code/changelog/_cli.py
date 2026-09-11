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


"""The console script: notes text on stdin, one answer on stdout.

**This module is the package's I/O boundary, and the only one.** Everything
under it is text in, text out -- no network, no git, no filesystem, no clock
-- and the test suite's `no_clock` fixture holds that line by making a
`datetime` call from the library modules fail. This file is deliberately
outside that fixture, because `--date` has to default to something and
"today" is the only sensible default for a workflow that runs on the day it
releases. If you find yourself wanting the clock, or a file, or an API call,
in any other module of this package: it goes here instead.

The shape is driven by how a GitHub Actions step consumes a result, which is
either as a `$GITHUB_OUTPUT` line or as a file. A `$GITHUB_OUTPUT` line takes
a scalar comfortably and a multi-line document only through a heredoc
delimiter that the document itself must not contain -- so the two commands
that emit Markdown emit it on stdout, for the step to redirect into a file,
and the two that emit a scalar emit a single bare word with no decoration, so
that `size=$(changelog bump-size < notes.md)` is the whole of the plumbing::

    gh api "repos/$REPO/releases/generate-notes" ... --jq .body > notes.md
    SIZE=$(changelog bump-size < notes.md)
    VERSION=$(changelog next-version --previous "$LAST_TAG" < notes.md)
    changelog release-notes < notes.md > release-notes.md
    changelog changes-entry --tag "$VERSION" < notes.md > changes-entry.md

Four invocations re-parse the same text four times, which costs nothing and
buys each step an output that goes where it belongs without any reshaping.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections.abc import Sequence

from ._format import format_changes, format_release_notes
from ._parse import parse_release_notes
from ._version import infer_bump_size, next_version


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='changelog',
        description=(
            "Turn GitHub's generated release-notes text, read from stdin, into "
            'our changelog format or into a version decision.'
        ),
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser(
        'bump-size',
        help="Print 'minor' or 'patch' for the changes in the notes.",
        description=(
            "Print 'minor' if the notes contain a feature or a breaking change, "
            "and 'patch' otherwise. Never 'major': that is a deliberate act, not "
            'something to infer. On a branch where a feature should not appear at '
            'all, such as a maintenance branch, treat a "minor" here as an error '
            'rather than releasing from it.'
        ),
    )

    next_version_parser = subparsers.add_parser(
        'next-version',
        help='Print the version that follows --previous, given the changes in the notes.',
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

    subparsers.add_parser(
        'release-notes',
        help='Print the release body, as Markdown.',
        description=(
            'Print the body of a GitHub release: the changes by category, '
            'breaking ones first, and the full-changelog link if the notes '
            'carried one.'
        ),
    )

    changes_entry_parser = subparsers.add_parser(
        'changes-entry',
        help='Print one CHANGES.md entry, as Markdown.',
        description=(
            'Print a single CHANGES.md entry for the release, to be prepended '
            'to the existing file.'
        ),
    )
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the notes on stdin and print the answer the subcommand asks for."""
    args = _build_parser().parse_args(argv)
    categories, full_changelog = parse_release_notes(sys.stdin.read())

    if args.command == 'bump-size':
        _emit(infer_bump_size(categories))
    elif args.command == 'next-version':
        try:
            _emit(next_version(args.previous, infer_bump_size(categories)))
        except ValueError as exc:
            print(f'changelog: {exc}', file=sys.stderr)
            return 2
    elif args.command == 'release-notes':
        _emit(format_release_notes(categories, full_changelog))
    else:
        _emit(format_changes(categories, args.tag, args.date or _today()))

    return 0


if __name__ == '__main__':
    sys.exit(main())
