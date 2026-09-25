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


"""Assemble the body of a GitHub release out of two things already written.

Neither half of the body is written here:

- The release notes come out of the merged release pull request's
  description, from between the `release-notes` markers. A human has read
  and edited them there, so they are taken exactly as they stand.
- The changelog is this version's section of `CHANGES.md`. It is already in
  the repository, written by `format_changes`, so it is copied rather than
  generated a second time: one source of truth, so the file and the release
  cannot drift.

The notes may be the placeholder `draft-release-notes` writes when it cannot
reach a model. That is not an error - somebody merged the pull request with it
in, which is their decision - so it goes into the body as it stands, and
`is_placeholder` lets the caller say so.
"""

from __future__ import annotations

import re

from ._constants import (
    CHANGES_SECTION_HEADING_REGEX,
    RELEASE_NOTES_END_REGEX,
    RELEASE_NOTES_PLACEHOLDER_REGEX,
    RELEASE_NOTES_START_REGEX,
)

# Any Markdown heading, for demoting the changelog's headings a level when
# they go under one of the release body's own. A generated changelog section
# is headings and bullets with no code fences in it, so a `#` at the start of
# a line is always a heading.
_HEADING = re.compile(r'^(#{1,5} )', re.MULTILINE)


def release_notes_from_description(description: str) -> str:
    """Return the release notes from between the markers in a description.

    Anything other than one start marker and one end marker after it is an
    error: the notes are the half of the release body a human wrote, and
    guessing at where they begin would be guessing at what gets published.

    Raises:
        ValueError: if the markers are missing, repeated, out of order, or
            have nothing between them.
    """
    starts = list(RELEASE_NOTES_START_REGEX.finditer(description))
    ends = list(RELEASE_NOTES_END_REGEX.finditer(description))
    for markers, name in ((starts, 'start'), (ends, 'end')):
        if len(markers) != 1:
            raise ValueError(
                f'the description has {len(markers)} `<!-- release-notes:{name} -->` markers,'
                ' and needs exactly one'
            )
    if ends[0].start() < starts[0].end():
        raise ValueError('the description ends the release notes before it starts them')
    notes = description[starts[0].end() : ends[0].start()].strip()
    if not notes:
        raise ValueError('there is nothing between the release-notes markers')
    return notes


def is_placeholder(notes: str) -> bool:
    """Return whether these notes are the "nobody drafted any" placeholder."""
    return bool(RELEASE_NOTES_PLACEHOLDER_REGEX.match(notes.strip()))


def changelog_section(changes: str, version: str) -> str:
    """Return the first section of a `CHANGES.md`, checked against the version.

    The first section is the release being made: the release pull request
    prepends it. It runs from its `# <version> - <date>` heading to the next
    `# ` heading, which is the previous release.

    Raises:
        ValueError: if the file does not start with a section heading, or the
            first section is for a different version.
    """
    lines = changes.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    heading = CHANGES_SECTION_HEADING_REGEX.match(lines[first]) if first is not None else None
    if not heading:
        raise ValueError('the changelog does not start with a `# <version> - <date>` heading')
    if heading.group('version') != version:
        raise ValueError(
            f"the changelog's first section is for {heading.group('version')},"
            f' but {version} is being released'
        )
    end = next(
        (i for i, line in enumerate(lines[first + 1 :], first + 1) if line.startswith('# ')),
        len(lines),
    )
    return '\n'.join(lines[first:end]).strip()


def release_body(notes: str, section: str) -> str:
    """Return the notes and the changelog section, as a release body.

    The notes come first and the changelog under them, which is the order they
    are read in: what this release is about, and then the complete list. The
    section keeps its own text exactly, and only its headings move: it arrives
    with a `# <version> - <date>` heading that the release already has as its
    title, and `## Category` headings that would outrank the `##` the notes
    are written in.
    """
    entries = _HEADING.sub(r'#\1', '\n'.join(section.splitlines()[1:]).strip())
    return f'{notes.strip()}\n\n---\n\n## Changelog\n\n{entries}\n'
