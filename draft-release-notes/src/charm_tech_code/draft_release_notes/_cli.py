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


"""The console script.

**No key means no notes, not a failed workflow.** Whenever the model cannot be
reached - no `OPENROUTER_API_KEY`, no `OPENROUTER_MODEL`, or a call that fails
- this writes a short placeholder telling the reviewer to write the notes
themselves, and exits successfully. The release must not be blocked by the
drafting of prose that a human is going to rewrite anyway. The title's
summary, when asked for with `--title-output`, works the same way.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from collections.abc import Sequence

from ._draft import (
    commit_digest,
    placeholder,
    split_title,
    system_prompt,
    tidy,
    title_placeholder,
    user_prompt,
)
from ._openrouter import call_openrouter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='draft-release-notes',
        description=(
            'Draft the release notes for a release with a model, or write a '
            'placeholder asking for them, and always succeed. Reads '
            'OPENROUTER_API_KEY and OPENROUTER_MODEL from the environment.'
        ),
    )
    parser.add_argument('--repo', required=True, metavar='OWNER/NAME')
    parser.add_argument('--version', required=True, metavar='X.Y.Z')
    parser.add_argument('--previous', required=True, metavar='X.Y.Z')
    parser.add_argument('--branch', required=True)
    parser.add_argument(
        '--changelog',
        required=True,
        metavar='PATH',
        help='The generated changelog entry for this release.',
    )
    parser.add_argument(
        '--exemplars',
        default=None,
        metavar='PATH',
        help='Past release bodies to write in the register of. Optional.',
    )
    parser.add_argument('--compare-url', default=None, metavar='URL')
    parser.add_argument(
        '--newest-release',
        default=None,
        metavar='X.Y.Z',
        help=(
            'The newest release in the repository, from any branch. On a maintenance '
            'branch it says which series the fixes came from. Optional.'
        ),
    )
    parser.add_argument(
        '--commits',
        default=None,
        metavar='PATH',
        help=(
            "The range's commit messages, as git log --reverse --no-merges --name-only "
            "--format='%%x1e%%s%%x1f%%b%%x1f' prints them. Optional."
        ),
    )
    parser.add_argument(
        '--docs-url',
        default=None,
        metavar='URL',
        help=(
            'Where the documentation is published, so that a page a commit changed '
            'can be linked. Only used with --commits. Optional.'
        ),
    )
    parser.add_argument(
        '--docs-dir',
        default='docs',
        metavar='PATH',
        help='Where the documentation source is in the repository. Defaults to docs.',
    )
    parser.add_argument(
        '--output',
        required=True,
        metavar='PATH',
        help='Where to write the notes. Written whether or not a model was reached.',
    )
    parser.add_argument(
        '--title-output',
        default=None,
        metavar='PATH',
        help=(
            "Where to write a one-line summary for the release's title, the part "
            'after "X.Y.Z: ". Optional; written whether or not a model was reached.'
        ),
    )
    return parser


def _write(args: argparse.Namespace, notes: str, summary: str | None, why_no_summary: str) -> None:
    """Write the notes, and the summary or its placeholder if one was asked for."""
    pathlib.Path(args.output).write_text(notes)
    if args.title_output:
        text = summary or title_placeholder(args.version, why_no_summary)
        pathlib.Path(args.title_output).write_text(text + '\n')


def main(argv: Sequence[str] | None = None) -> int:
    """Draft the notes, or write the placeholder, and always succeed."""
    args = _build_parser().parse_args(argv)

    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    model = os.environ.get('OPENROUTER_MODEL', '')

    # Neither of these is an error. The key and the model are repository
    # settings, so a release cut before those settings exist gets a
    # placeholder and carries on.
    if not api_key:
        reason = 'no OPENROUTER_API_KEY is configured'
    elif not model:
        reason = 'no OPENROUTER_MODEL variable is set'
    else:
        reason = ''

    if reason:
        print(f'{reason}: writing the placeholder body.', file=sys.stderr)
        _write(args, placeholder(args.version, reason), None, reason)
        return 0

    exemplars = pathlib.Path(args.exemplars).read_text() if args.exemplars else ''
    commits = (
        commit_digest(
            pathlib.Path(args.commits).read_text(),
            docs_url=args.docs_url,
            docs_dir=args.docs_dir,
        )
        if args.commits
        else ''
    )
    system = system_prompt(args.repo, args.version)
    user = user_prompt(
        repo=args.repo,
        version=args.version,
        previous=args.previous,
        branch=args.branch,
        changelog=pathlib.Path(args.changelog).read_text(),
        exemplars=exemplars,
        compare_url=args.compare_url,
        commits=commits,
        newest=args.newest_release,
    )
    try:
        answer = tidy(call_openrouter(system, user, model, api_key))
    except RuntimeError as exc:
        print(f'the draft failed ({exc}): writing the placeholder body.', file=sys.stderr)
        reason = f'the draft failed ({exc})'
        _write(args, placeholder(args.version, reason), None, reason)
        return 0

    summary, notes = split_title(answer)
    if not notes:
        print('the model answered with nothing: writing the placeholder body.', file=sys.stderr)
        reason = 'the model answered with nothing'
        _write(args, placeholder(args.version, reason), summary, reason)
        return 0

    _write(args, notes + '\n', summary, 'the model did not suggest one')
    print(
        f'{args.output}: {len(notes)} characters, drafted by {model};'
        f' title {"summary " + repr(summary) if summary else "not suggested"}.',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
