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


"""Turn GitHub's generated release-notes text into our changelog format.

Text in, structured data and formatted strings out. Nothing here touches the
network, git, the filesystem or the clock, so a caller supplies the notes
text and the date and decides what to do with what comes back::

    categories, full_changelog = parse_release_notes(notes_text)
    notes = format_release_notes(categories, full_changelog)
    entry = format_changes(categories, '3.8.2', datetime.date.today())

The format is the package's own, not a parameter -- see `_constants` for
what that means and why `chore` commits do not appear in a changelog.
"""

from __future__ import annotations

from ._constants import CATEGORIES, CATEGORY_HEADINGS
from ._format import commit_type_to_category, format_changes, format_release_notes
from ._parse import parse_release_notes

__all__ = [
    'CATEGORIES',
    'CATEGORY_HEADINGS',
    'commit_type_to_category',
    'format_changes',
    'format_release_notes',
    'parse_release_notes',
]
