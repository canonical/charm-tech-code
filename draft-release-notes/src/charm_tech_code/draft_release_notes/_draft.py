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


"""Build the prompts, and tidy what comes back."""

from __future__ import annotations

import importlib.resources
import re

# The release pull request's description wraps the notes in these, so that
# the release body can be lifted back out of it later (the `changelog`
# package's `release-body`). A model that emits one of them itself would
# truncate its own notes, so they are stripped from whatever comes back.
MARKERS = re.compile(r'<!--\s*release-notes:(?:start|end)\s*-->')

# A model told to emit Markdown and nothing else sometimes wraps the lot in a
# fence anyway.
WRAPPING_FENCE = re.compile(r'\A```(?:markdown|md)?\n(?P<body>.*)\n```\s*\Z', re.DOTALL)


def system_prompt(repo: str, version: str) -> str:
    """Return the system prompt, with the release filled in."""
    template = importlib.resources.files(__package__).joinpath('prompt.md').read_text()
    return template.replace('<repo>', repo).replace('<version>', version)


def user_prompt(
    *,
    repo: str,
    version: str,
    previous: str,
    branch: str,
    changelog: str,
    exemplars: str = '',
    compare_url: str | None = None,
) -> str:
    """Return the user message: everything about this particular release.

    The generated changelog, the range it covers, and the exemplar releases,
    if the caller has any.
    """
    parts = [
        '# This release',
        '',
        f'Repository: {repo}',
        f'Version: {version}',
        f'Previous release: {previous}',
        f'Branch: {branch}',
        f'Commit range: {previous}..{branch}',
    ]
    if compare_url:
        parts.append(f'Compare: {compare_url}')
    parts += ['', '# The generated changelog for this release', '', changelog.strip()]
    if exemplars.strip():
        parts += ['', '# Exemplar releases', '', exemplars.strip()]
    return '\n'.join(parts) + '\n'


def tidy(notes: str) -> str:
    """Return the model's Markdown with the two things it gets wrong removed."""
    notes = notes.strip()
    fence = WRAPPING_FENCE.match(notes)
    if fence:
        notes = fence.group('body').strip()
    return MARKERS.sub('', notes).strip()


def placeholder(version: str, reason: str) -> str:
    """Return the body to use when there is no draft: a note asking for one.

    The first line is what the `changelog` package's `release-body`
    recognises as the placeholder, so keep its opening words as they are.
    """
    return (
        f'_No release notes were drafted for {version}: {reason}._\n'
        '\n'
        'Write them here before merging. They become the body of the GitHub'
        ' release, above the changelog entry for this version.\n'
    )
