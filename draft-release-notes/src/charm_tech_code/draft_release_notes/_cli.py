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
drafting of prose that a human is going to rewrite anyway.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from collections.abc import Sequence

from ._draft import placeholder, system_prompt, tidy, user_prompt
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
        '--output',
        required=True,
        metavar='PATH',
        help='Where to write the notes. Written whether or not a model was reached.',
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Draft the notes, or write the placeholder, and always succeed."""
    args = _build_parser().parse_args(argv)

    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    model = os.environ.get('OPENROUTER_MODEL', '')
    output = pathlib.Path(args.output)

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
        output.write_text(placeholder(args.version, reason))
        return 0

    exemplars = pathlib.Path(args.exemplars).read_text() if args.exemplars else ''
    system = system_prompt(args.repo, args.version)
    user = user_prompt(
        repo=args.repo,
        version=args.version,
        previous=args.previous,
        branch=args.branch,
        changelog=pathlib.Path(args.changelog).read_text(),
        exemplars=exemplars,
        compare_url=args.compare_url,
    )
    try:
        notes = tidy(call_openrouter(system, user, model, api_key))
    except RuntimeError as exc:
        print(f'the draft failed ({exc}): writing the placeholder body.', file=sys.stderr)
        output.write_text(placeholder(args.version, f'the draft failed ({exc})'))
        return 0

    if not notes:
        print('the model answered with nothing: writing the placeholder body.', file=sys.stderr)
        output.write_text(placeholder(args.version, 'the model answered with nothing'))
        return 0

    output.write_text(notes + '\n')
    print(f'{output}: {len(notes)} characters, drafted by {model}.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
