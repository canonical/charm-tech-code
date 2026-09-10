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


"""Parsing GitHub's generated release-notes text into categories."""

from __future__ import annotations

from ._constants import (
    BREAKING,
    CATEGORIES,
    CHANGE_LINE_REGEX,
    FULL_CHANGELOG_PREFIX,
    NEW_CONTRIBUTORS_REGEX,
)


def parse_release_notes(release_notes: str) -> tuple[dict[str, list[tuple[str, str]]], str | None]:
    """Parse auto-generated release notes into categories.

    The input is GitHub's *generated* release-notes text, not a ``git log``.
    GitHub builds it from the titles of the pull requests merged in the
    range, one ``* type!: summary by @user in <url>`` bullet each, which is
    why this reads conventional-commit types off PR titles rather than off
    commit subjects. How a caller obtains that text is the caller's problem:
    a release already has it in its body, and a workflow running before any
    release exists can ask for a preview of it. Nothing here does I/O.

    The "New Contributors" section is removed. Bullets whose type is not a
    changelog category -- `chore`, most of all -- are dropped; see
    ``_constants.CATEGORIES`` for why that is deliberate. The full-changelog
    line is returned separately rather than categorised.

    Returns:
        A tuple containing:
        - A dict with conventional commit types as keys and lists of tuples
          (description, PR link) as values. Every category is present, even
          when empty, in the order they are rendered in.
        - The full changelog line if present, or ``None`` if not found.
    """
    release_notes = NEW_CONTRIBUTORS_REGEX.sub(r'\2', release_notes)
    categories: dict[str, list[tuple[str, str]]] = {category: [] for category in CATEGORIES}
    full_changelog_line = None

    for line in release_notes.splitlines():
        if match := CHANGE_LINE_REGEX.match(line.strip()):
            category = match.group('category').strip()
            if category in categories:
                description = match.group('summary').strip()
                description = description[0].upper() + description[1:]
                pr_link = match.group('pr').strip()
                if match.group('breaking') == '!':
                    categories[BREAKING].append((
                        f'{category.capitalize()}: {description}',
                        pr_link,
                    ))
                else:
                    categories[category].append((description, pr_link))

        elif line.startswith(FULL_CHANGELOG_PREFIX):
            full_changelog_line = line

    return categories, full_changelog_line
