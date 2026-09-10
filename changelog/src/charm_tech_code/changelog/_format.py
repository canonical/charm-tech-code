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


"""Rendering parsed categories as release notes and as a changelog entry."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping

from ._constants import (
    BREAKING,
    BREAKING_PREAMBLE,
    CATEGORY_HEADINGS,
    PR_LINK_REGEX,
)

logger = logging.getLogger(__name__)


def commit_type_to_category(commit_type: str) -> str:
    """Map a commit type to a human-readable category heading.

    If the commit type is not recognised, it returns the capitalised commit type.
    """
    return CATEGORY_HEADINGS.get(commit_type, commit_type.capitalize())


def format_release_notes(
    categories: Mapping[str, list[tuple[str, str]]], full_changelog: str | None
) -> str:
    """Format for release notes.

    Results in a Markdown formatted string with sections for each commit type.
    If `full_changelog` is provided, it is appended at the end.

    Breaking changes are rendered first, under their own heading and a
    sentence asking the reader to review them. `categories` is expected to
    be what `parse_release_notes` returned: every category present, in the
    order they are rendered in.
    """
    lines = ["## What's Changed", '']
    if categories[BREAKING]:
        lines.append(f'### {commit_type_to_category(BREAKING)}')
        lines.append(f'{BREAKING_PREAMBLE}\n')
        for description, pr_link in categories[BREAKING]:
            lines.append(f'* {description} in {pr_link}')
        lines.append('')
        logger.info(
            'Breaking changes detected in the release notes. '
            'Please ensure there are sufficient instructions for users to handle them.'
        )
    for commit_type, items in categories.items():
        if commit_type == BREAKING:
            continue
        if items:
            lines.append(f'### {commit_type_to_category(commit_type)}')
            for description, pr_link in items:
                lines.append(f'* {description} in {pr_link}')
            lines.append('')
    if full_changelog:
        lines.append(full_changelog)
    return '\n'.join(lines)


def format_changes(
    categories: Mapping[str, list[tuple[str, str]]], tag: str, date: datetime.date
) -> str:
    """Format for CHANGES.md.

    The header is formatted as a top-level heading with the tag and date.
    The content is a Markdown formatted string with sections for each commit type.
    Each item is formatted as a bullet point with the description and PR number in parentheses.

    `date` is passed in rather than read from the clock. This module does no
    I/O of any kind, and "what day is it" is I/O: the caller knows whether it
    means the runner's today, the date on the tag, or a date under test.
    """
    day = date.strftime('%d %B %Y')
    lines = [f'# {tag} - {day}\n']
    for commit_type, items in categories.items():
        if items:
            lines.append(f'## {commit_type_to_category(commit_type)}\n')
            for description, pr_link in items:
                pr_num = '?'
                match = PR_LINK_REGEX.match(pr_link)
                if match:
                    pr_num = match.group(1)
                lines.append(f'* {description} (#{pr_num})')
            lines.append('')
    return '\n'.join(lines) + '\n'
