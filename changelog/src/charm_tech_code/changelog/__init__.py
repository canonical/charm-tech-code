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


"""Turn a range of commits into our changelog format.

Text in, structured data and formatted strings out. Nothing here touches the
network, git, the filesystem or the clock, so a caller supplies the log text
and the date and decides what to do with what comes back::

    log = subprocess.run(
        ['git', 'log', '--reverse', '--no-merges', f'--format={GIT_LOG_FORMAT}', '3.8.1..3.8.2'],
        capture_output=True, text=True, check=True,
    ).stdout
    categories = parse_git_log(log, team=MAINTAINERS, repo='canonical/operator')
    notes = format_release_notes(categories, None, repo='canonical/operator')
    entry = format_changes(categories, '3.8.2', datetime.date.today())

The same parse answers how big a release the range adds up to, and what that
makes the version after `previous`::

    size = infer_bump_size(categories)
    version = next_version(previous, size)

`parse_release_notes` is the other door in, reading GitHub's generated
release-notes text instead of the commits. It describes the same pull
requests by their *titles*, which is a weaker source -- a title is written
once, at open time, while the convention governs the commits -- and it
cannot resolve a revert at all, because that needs a commit body. Prefer
`parse_git_log`; see `_parse` for the full list of differences.

The format is the package's own, not a parameter -- see `_constants` for
what that means and why `chore` commits do not appear in a changelog. The
`changelog` console script (`_cli`) wraps all of the above for a workflow
step, and is the one place in the package that does any I/O.
"""

from __future__ import annotations

from ._constants import (
    CATEGORIES,
    CATEGORY_HEADINGS,
    GIT_LOG_FORMAT,
    MINOR_BUMP_CATEGORIES,
)
from ._format import commit_type_to_category, format_changes, format_release_notes
from ._models import Change
from ._parse import parse_git_log, parse_release_notes
from ._version import MINOR, PATCH, BumpSize, infer_bump_size, next_version

__all__ = [
    'CATEGORIES',
    'CATEGORY_HEADINGS',
    'GIT_LOG_FORMAT',
    'MINOR',
    'MINOR_BUMP_CATEGORIES',
    'PATCH',
    'BumpSize',
    'Change',
    'commit_type_to_category',
    'format_changes',
    'format_release_notes',
    'infer_bump_size',
    'next_version',
    'parse_git_log',
    'parse_release_notes',
]
