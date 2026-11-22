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


"""Suggestions for a pull request title, before it becomes a changelog line.

A squash-merged pull request's title is the commit subject, and the commit
subject is the changelog bullet. Fixing a title when the pull request is
open costs its author one edit; fixing it in the release pull request costs
the reviewer one suggestion per line, all at once.

These are suggestions, not rules. Each check is a heuristic, and a title
that deliberately breaks one (a name that really is lower case, an
abbreviation that is the name of something) is fine as it stands. A caller
should show them, not fail on them.
"""

from __future__ import annotations

import re

from ._constants import CODE_SPAN_REGEX, COMMIT_SUBJECT_REGEX, PR_SUFFIX_REGEX
from ._parse import code_spans

#: Abbreviations to spell out, and what to spell them out as. Each is matched
#: as a whole word, outside backticks, so `k8s` in a package name in
#: backticks is left alone.
ABBREVIATIONS: dict[str, str] = {
    'K8s': 'Kubernetes',
    'k8s': 'Kubernetes',
    'deps': 'dependencies',
    'dep': 'dependency',
    'e.g.': 'for example',
    'i.e.': 'that is',
}

#: Product names, as they are written in prose. A lower-case one outside
#: backticks is most likely the product rather than the package or the
#: command, which would belong in backticks.
PRODUCT_NAMES: tuple[str, ...] = (
    'Charmcraft',
    'Charmhub',
    'Concierge',
    'Jubilant',
    'Juju',
    'Kubernetes',
    'Pebble',
)


def _words(text: str, word: str) -> bool:
    """Whether `word` is in `text` as a word of its own, not part of a longer name.

    A hyphen counts as part of a name, so `juju` does not match in
    `juju-http-proxy`, a dot does too, so `deps` does not match in
    `deps.txt`, and so does a slash, so `juju` does not match in
    `canonical.com/juju` or `juju/4`.
    """
    pattern = rf'(?<![\w./-]){re.escape(word)}(?![\w/-]|\.\w)'
    if word.endswith('.'):
        pattern = rf'(?<![\w./-]){re.escape(word)}'
    return re.search(pattern, text) is not None


def title_suggestions(title: str) -> list[str]:
    """Return suggestions for improving a pull request title, one sentence each.

    Only the summary after the conventional-commit type is looked at.
    Whether the type is valid is a different check, so a title that is not
    a conventional-commit one gets no suggestions here rather than an error.
    """
    title = title.strip()
    if suffix := PR_SUFFIX_REGEX.search(title):
        title = title[: suffix.start()]
    match = COMMIT_SUBJECT_REGEX.match(title)
    if not match:
        return []
    summary = match.group('summary').strip()
    prose = CODE_SPAN_REGEX.sub(' ', summary)

    suggestions: list[str] = []

    wrapped = code_spans(summary)
    if wrapped != summary:
        before = set(CODE_SPAN_REGEX.findall(summary))
        names = [span for span in CODE_SPAN_REGEX.findall(wrapped) if span not in before]
        suggestions.append(f'Put code in backticks: {", ".join(names)}.')

    for short, long in ABBREVIATIONS.items():
        if _words(prose, short):
            suggestions.append(f'Write "{long}" rather than "{short}".')

    for name in PRODUCT_NAMES:
        lower = name.lower()
        if _words(prose, lower):
            suggestions.append(
                f'Write "{name}" with a capital, if it means the product. If it means '
                f'the package or the command, put `{lower}` in backticks.'
            )

    return suggestions
