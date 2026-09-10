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


"""The changelog format, as constants.

None of this is injectable, and that is the point. The format is the same
across the Charm Tech repositories, and the set of conventional-commit types
is enforced by a shared CI check, so there is no second format for an
adopting repository to supply. A hook or a template system here would exist
for a caller that does not exist.
"""

from __future__ import annotations

import re

#: The bullet format of GitHub's generated release notes:
#: ``* type!: summary by @user in https://github.com/owner/repo/pull/123``.
#: The ``!`` is optional and marks a breaking change.
CHANGE_LINE_REGEX = re.compile(
    r'^\* (?P<category>\w+)(?P<breaking>!?): (?P<summary>.*) by [^ ]+ in (?P<pr>.*)'
)

#: The PR link in a bullet, from which the ``(#123)`` in a ``CHANGES.md``
#: entry is taken.
PR_LINK_REGEX = re.compile(r'https?://[^ ]+/pull/(\d+)')

#: GitHub appends a section of first-time contributors to its generated
#: notes. It is not part of the changelog, so it is stripped before parsing.
NEW_CONTRIBUTORS_REGEX = re.compile(r'(## New Contributors.*?)(\n|$)', flags=re.DOTALL)

#: The line GitHub ends its generated notes with, carrying a compare link.
#: It is passed through to the release notes unchanged.
FULL_CHANGELOG_PREFIX = '**Full Changelog**'

#: The categories a changelog has, in the order they are rendered.
#:
#: This is also the filter. A conventional-commit type that is not a key here
#: is dropped from the changelog entirely, and `chore` is the type that makes
#: that matter: it is a real type, accepted by the PR-title check, but it is
#: deliberately not a category. Dependency bumps, charm-pin updates and the
#: release's own version-bump commit are all `chore`, and none of them is
#: something a reader of a changelog is looking for. In a typical operator
#: release that is a third to a half of the commits in the range. Dropping
#: them is the intended behaviour, not an oversight in the type list, so
#: please do not "fix" it by adding a `chore` key.
#:
#: `breaking` goes the other way round: it is a key here but is not a
#: conventional-commit type, so nothing ever parses into it directly. A `!`
#: after the real type moves an entry into it instead, keeping its real type
#: as a prefix (`Feat: ...`), and it renders first.
CATEGORIES: tuple[str, ...] = (
    'breaking',
    'feat',
    'fix',
    'docs',
    'test',
    'refactor',
    'perf',
    'ci',
    'revert',
)

#: The meta category breaking changes are collected into.
BREAKING = 'breaking'

#: Commit type to the heading it is rendered under. A type with no entry
#: here is capitalised instead, which is what makes an unrecognised type
#: degrade to something readable rather than to a KeyError.
CATEGORY_HEADINGS = {
    'feat': 'Features',
    'fix': 'Fixes',
    'docs': 'Documentation',
    'test': 'Tests',
    'ci': 'CI',
    'perf': 'Performance',
    'refactor': 'Refactoring',
    'revert': 'Reverted',
    'breaking': 'Breaking Changes',
}

#: The sentence under the release notes' `### Breaking Changes` heading. A
#: `!` deliberately does not infer a major version bump -- a breaking change
#: sometimes rides in a minor release -- so this calling-out is what the bent
#: rule relies on.
BREAKING_PREAMBLE = 'There are breaking changes in this release. Please review them carefully:'
