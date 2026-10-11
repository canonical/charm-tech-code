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


"""Assemble a GitHub release's title and body out of things already written.

Neither half of the body is written here:

- The release notes come out of the merged release pull request's
  description, from between the `release-notes` markers. A human has read
  and edited them there, so they are taken exactly as they stand.
- The changelog is this version's section of `CHANGES.md`. It is already in
  the repository, written by `format_changes`, so it is copied rather than
  generated a second time: one source of truth, so the file and the release
  cannot drift.

The body ends by thanking whoever the changelog credits. That is built here
rather than drafted with the notes, so that nobody is mentioned in the release
pull request: a contributor should be notified about the release, not about
the pull request that prepares it.

The title's summary comes out of the same description, from between the
`release-title` markers, and the version in front of it is added here.

The notes may be the placeholder `draft-release-notes` writes when it cannot
reach a model. That is not an error - somebody merged the pull request with it
in, which is their decision - so it goes into the body as it stands, and
`is_placeholder` lets the caller say so. A title is different: a release can
go out without a summary, so a missing or placeholder summary leaves the bare
version as the title rather than stopping anything.
"""

from __future__ import annotations

import re

from ._constants import (
    ALL_COMMITS_PREFIX,
    CHANGES_CREDIT_REGEX,
    CHANGES_SECTION_HEADING_REGEX,
    RELEASE_NOTES_END_REGEX,
    RELEASE_NOTES_PLACEHOLDER_REGEX,
    RELEASE_NOTES_START_REGEX,
    RELEASE_TITLE_END_REGEX,
    RELEASE_TITLE_PLACEHOLDER_REGEX,
    RELEASE_TITLE_START_REGEX,
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
    notes = _between_markers(
        _unix_newlines(description),
        RELEASE_NOTES_START_REGEX,
        RELEASE_NOTES_END_REGEX,
        'release-notes',
    )
    if not notes:
        raise ValueError('there is nothing between the release-notes markers')
    return notes


def release_summary_from_description(description: str) -> str | None:
    """Return the title's summary from between its markers, or None if there are none.

    A description with no `release-title` markers at all has no summary, which
    is not an error: it only means the release is titled with its version.
    Markers that are there but broken are an error, the same as for the
    notes, because they are somebody's edit gone wrong rather than an absence.

    Raises:
        ValueError: if only one kind of marker is there, either is repeated,
            or they are out of order.
    """
    description = _unix_newlines(description)
    if not (
        RELEASE_TITLE_START_REGEX.search(description)
        or RELEASE_TITLE_END_REGEX.search(description)
    ):
        return None
    return _between_markers(
        description, RELEASE_TITLE_START_REGEX, RELEASE_TITLE_END_REGEX, 'release-title'
    )


def _unix_newlines(description: str) -> str:
    # GitHub's web editor saves a description with CRLF line endings, and a
    # marker regex's `$` does not match before the `\r`.
    return description.replace('\r\n', '\n')


def _between_markers(
    description: str, start: re.Pattern[str], end: re.Pattern[str], name: str
) -> str:
    starts = list(start.finditer(description))
    ends = list(end.finditer(description))
    for markers, which in ((starts, 'start'), (ends, 'end')):
        if len(markers) != 1:
            raise ValueError(
                f'the description has {len(markers)} `<!-- {name}:{which} -->` markers,'
                ' and needs exactly one'
            )
    if ends[0].start() < starts[0].end():
        what = 'release notes' if name == 'release-notes' else 'release title'
        pronoun = 'them' if name == 'release-notes' else 'it'
        raise ValueError(f'the description ends the {what} before it starts {pronoun}')
    return description[starts[0].end() : ends[0].start()].strip()


def release_title(version: str, summary: str | None) -> str:
    """Return the release's title: `X.Y.Z: <summary>`, or the bare version.

    The version is always added here, and taken off the front of the summary
    if somebody typed it there too, so the title cannot name a different
    version from the release it is on. The summary is folded onto one line,
    and a closing full stop goes, since a title is not a sentence. No summary,
    or the placeholder, gives the bare version.
    """
    if summary is None or is_title_placeholder(summary):
        return version
    text = ' '.join(summary.split())
    text = re.sub(rf'^{re.escape(version)}\s*[:-]\s*', '', text).removesuffix('.').strip()
    return f'{version}: {text}' if text else version


def is_title_placeholder(summary: str) -> bool:
    """Return whether this summary is the "nobody suggested one" placeholder."""
    return bool(RELEASE_TITLE_PLACEHOLDER_REGEX.match(summary.strip()))


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


def release_body(notes: str, section: str, compare_url: str | None = None) -> str:
    """Return the notes and the changelog section, as a release body.

    The notes come first and the changelog under them, which is the order they
    are read in: what this release is about, and then the complete list. The
    section keeps its own text exactly, and only its headings move: it arrives
    with a `# <version> - <date>` heading that the release already has as its
    title, and `## Category` headings that would outrank the `##` the notes
    are written in.

    With a `compare_url`, the changelog is followed by an "All commits" line
    linking to it. The caller supplies it because the previous release is the
    caller's to know.

    The very last line thanks the contributors the section credits, if it
    credits anyone; see `thanks`.
    """
    entries = _HEADING.sub(r'#\1', '\n'.join(section.splitlines()[1:]).strip())
    body = f'{notes.strip()}\n\n---\n\n## Changelog\n\n{entries}\n'
    if compare_url:
        body += f'\n{ALL_COMMITS_PREFIX}: {compare_url}\n'
    if line := thanks(section):
        body += f'\n{line}\n'
    return body


def thanks(section: str) -> str | None:
    """Return a sentence thanking the people a changelog section credits.

    The credits are read back out of the section's entries rather than passed
    in, because the section is what a human has reviewed: a credit removed
    from `CHANGES.md` in the release pull request is not thanked, and one
    added there is. Each person is thanked once, in the order they first
    appear. A section that credits nobody gives `None`, and no sentence.
    """
    people: list[str] = []
    for match in CHANGES_CREDIT_REGEX.finditer(section):
        person = (match.group('handle') or match.group('name')).strip()
        if person not in people:
            people.append(person)
    if not people:
        return None
    if len(people) == 1:
        return f'Thanks {people[0]} for your contribution to this release!'
    names = people[0] if len(people) == 2 else ', '.join(people[:-1]) + ','
    return f'Thanks {names} and {people[-1]} for your contributions to this release!'
