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

**This module is the package's I/O boundary, and the only one.** The clock is
read here and nowhere else, and so is anything else that is not text in, text
out: a file, a network call, git itself.

Three subcommands do not read a git log at all, because they are the version
and release-body decisions a release pipeline makes after the changelog is
written: `detect-release`, `post-release` and `release-body`. The two that
answer with more than one value print `key=value` lines, which a workflow
step can append to `$GITHUB_OUTPUT` as they stand.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import sys
import textwrap
from collections.abc import Sequence

from ._constants import GIT_LOG_FORMAT
from ._format import format_changes, format_release_notes
from ._parse import parse_git_log
from ._release import detect_release, is_prerelease, next_dev_version, resolve_branch
from ._release_body import (
    changelog_section,
    is_placeholder,
    release_body,
    release_notes_from_description,
)
from ._version import infer_bump_size, next_version


def _today() -> datetime.date:
    """Return the default for `--date`, the package's only reading of the clock.

    UTC rather than local time: the runner is UTC, and a release's date
    should not depend on who ran it from where.

    Called where `--date` is used rather than passed as its `default=`: the
    parser is built for every subcommand, and `bump-size` has no business
    reading the clock to answer "minor or patch".
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
    """Build the parent parser for the options that say what arrives on stdin.

    Shared by the four subcommands that read it, as a parent parser, so that
    a caller switching input path changes one flag on every command rather
    than learning four spellings of it.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        '--team',
        default='',
        metavar='EMAIL-OR-HANDLE,...',
        help=(
            'Authors not to credit, comma-separated, as email addresses '
            'and/or GitHub handles. These are the people who maintain the '
            'repository; everyone else is credited by handle, or by name '
            'where no handle can be worked out. The default credits everyone.'
        ),
    )
    return parser


def _repo_option(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument(
        '--repo',
        required=required,
        metavar='OWNER/NAME',
        help=(
            'The repository this log came from. A change carries a pull '
            'request number rather than a URL -- a number is all a git log '
            'has -- so the links in a CHANGES.md entry are built from this. '
            'It also tells a `Reverts` line naming another repository apart '
            'from one naming this one.'
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='changelog',
        description=(
            'Turn a range of changes, read from stdin, into our changelog '
            'format or into a version decision.'
        ),
        epilog=textwrap.dedent("""\
            A release pipeline, end to end:

              git log --reverse --no-merges --format="$(changelog git-log-format)" \\
                  "$LAST_TAG..$BRANCH" > log.txt
              SIZE=$(changelog bump-size --team "$TEAM" < log.txt)
              VERSION=$(changelog next-version --previous "$LAST_TAG" --team "$TEAM" < log.txt)
              changelog release-notes --repo "$REPO" --team "$TEAM" < log.txt > release-notes.md
              changelog changes-entry --repo "$REPO" --tag "$VERSION" --team "$TEAM" \\
                  < log.txt > changes-entry.md
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    _repo_option(release_notes_parser, required=False)
    release_notes_parser.add_argument(
        '--compare-url',
        default=None,
        metavar='URL',
        help=(
            'The compare link to end on. A git log carries no such link, and '
            "the tags at either end of the range are the caller's to know, so "
            'this is how to have one. Omit it for no link at all.'
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
    _repo_option(changes_entry_parser, required=True)
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

    detect_release_parser = subparsers.add_parser(
        'detect-release',
        help='Print the version a push releases, or nothing if it is not a release.',
        description=(
            'Decide whether a push to a release branch is a release: the version '
            'changed, and the new one has no .devN suffix. Prints version= and '
            'prerelease= lines when it is, and nothing when it is not. Either way '
            'the reason goes to stderr.'
        ),
    )
    detect_release_parser.add_argument(
        '--after',
        required=True,
        metavar='VERSION',
        help='The version the push left behind.',
    )
    detect_release_parser.add_argument(
        '--before',
        default=None,
        metavar='VERSION',
        help='The version before the push. Leave it out if there was none.',
    )

    post_release_parser = subparsers.add_parser(
        'post-release',
        help='Print the branch a release came from and the version it goes to now.',
        description=(
            'Work out which branch a published release was cut from, and the '
            'development version that branch goes to now. Prints branch= and '
            'version= lines.'
        ),
    )
    post_release_parser.add_argument(
        '--tag', required=True, metavar='X.Y.Z', help='The tag of the release that was published.'
    )
    post_release_parser.add_argument(
        '--target',
        default='',
        metavar='COMMITTISH',
        help="The release's target_commitish: a branch name, or a commit SHA.",
    )
    post_release_parser.add_argument(
        '--candidates',
        default='',
        metavar='A,B',
        help='Every branch the repository releases from, comma-separated.',
    )
    post_release_parser.add_argument(
        '--containing',
        default='',
        metavar='A,B',
        help='Those of them whose history contains the released tag.',
    )
    post_release_parser.add_argument(
        '--default-branch',
        default='main',
        metavar='NAME',
        help='The branch that wins when several contain the tag. Defaults to main.',
    )

    release_body_parser = subparsers.add_parser(
        'release-body',
        help='Print a release body: the notes from a description, then the changelog.',
        description=(
            'Read a merged release pull request description on stdin, take the '
            'release notes from between its release-notes markers, and print them '
            "followed by the version's section of the changelog."
        ),
    )
    release_body_parser.add_argument(
        '--version', required=True, metavar='X.Y.Z', help='The version being released.'
    )
    release_body_parser.add_argument(
        '--changes',
        default='CHANGES.md',
        metavar='PATH',
        help='The changelog, whose first section is this release. Defaults to CHANGES.md.',
    )

    return parser


def _split(value: str) -> list[str]:
    """Return a comma-separated list, with the empties dropped."""
    return [item.strip() for item in value.split(',') if item.strip()]


def _detect_release(args: argparse.Namespace) -> int:
    version, why = detect_release(args.before or None, args.after)
    if version is None:
        print(f'Not a release: {why}.', file=sys.stderr)
        return 0
    print(f'Releasing {version}: {why}.', file=sys.stderr)
    _emit(f'version={version}\nprerelease={str(is_prerelease(version)).lower()}')
    return 0


def _post_release(args: argparse.Namespace) -> int:
    try:
        branch, why = resolve_branch(
            args.target,
            _split(args.candidates),
            _split(args.containing),
            default_branch=args.default_branch,
        )
        version = next_dev_version(args.tag, branch)
    except ValueError as exc:
        print(f'changelog: {exc}', file=sys.stderr)
        return 2
    print(f'{args.tag} was released from {branch}: {why}.', file=sys.stderr)
    print(f'{branch} goes to {version}.', file=sys.stderr)
    _emit(f'branch={branch}\nversion={version}')
    return 0


def _release_body(args: argparse.Namespace) -> int:
    try:
        notes = release_notes_from_description(sys.stdin.read())
        section = changelog_section(pathlib.Path(args.changes).read_text(), args.version)
    except (OSError, ValueError) as exc:
        print(f'changelog: {exc}', file=sys.stderr)
        return 2
    if is_placeholder(notes):
        print(
            f'The {args.version} pull request was merged with the release-notes '
            'placeholder in it, so the body carries that instead of notes.',
            file=sys.stderr,
        )
    _emit(release_body(notes, section))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the changes on stdin and print the answer the subcommand asks for."""
    args = _build_parser().parse_args(argv)

    if args.command == 'git-log-format':
        _emit(GIT_LOG_FORMAT)
        return 0
    if args.command == 'detect-release':
        return _detect_release(args)
    if args.command == 'post-release':
        return _post_release(args)
    if args.command == 'release-body':
        return _release_body(args)

    categories = parse_git_log(
        sys.stdin.read(),
        # A workflow passes the team as one repository variable with commas
        # in it, which is the only spelling `--team` takes. Empty entries are
        # dropped by `normalise_team`.
        team=args.team.split(','),
        # Only `release-notes` and `changes-entry` take `--repo`.
        repo=getattr(args, 'repo', None),
    )

    if args.command == 'bump-size':
        _emit(infer_bump_size(categories))
    elif args.command == 'next-version':
        try:
            _emit(next_version(previous=args.previous, size=infer_bump_size(categories)))
        except ValueError as exc:
            print(f'changelog: {exc}', file=sys.stderr)
            return 2
    elif args.command == 'release-notes':
        _emit(format_release_notes(categories, args.compare_url))
    else:
        _emit(format_changes(categories, args.tag, args.date or _today(), repo=args.repo))

    return 0


if __name__ == '__main__':
    sys.exit(main())
