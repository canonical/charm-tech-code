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

"""Fix: copy the CONTRIBUTING.md template into the repo root.

The owner/repo placeholders are rewritten to match origin. The template
mirrors the dominant Charm Tech pattern (substantive standalone doc with a
`# Pull requests` section).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from ..common import ASSETS, baseline_slug, repo_root

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    """Copy the CONTRIBUTING.md template into place, and return the exit code."""
    try:
        os.chdir(repo_root())
    except OSError:
        return 3

    if Path('CONTRIBUTING.md').exists():
        sys.stderr.write('CONTRIBUTING.md already exists; refusing to overwrite.\n')
        return 1

    template = ASSETS / 'CONTRIBUTING.md.template'
    if not template.is_file():
        sys.stderr.write('Template missing.\n')
        return 3

    shutil.copy(template, 'CONTRIBUTING.md')

    slug = baseline_slug()
    if slug:
        # Match shell: owner=${slug%%/*}, name=${slug##*/}.
        owner = slug.split('/', 1)[0]
        name = slug.rsplit('/', 1)[-1]
        text = Path('CONTRIBUTING.md').read_text()
        text = text.replace('REPLACE_WITH_OWNER', owner).replace('REPLACE_WITH_REPO', name)
        Path('CONTRIBUTING.md').write_text(text)
        sys.stdout.write(f'Rewrote owner/repo placeholders to {owner}/{name}.\n')
    else:
        sys.stderr.write(
            'Could not determine origin slug; left REPLACE_WITH_OWNER/REPO placeholders in '
            'CONTRIBUTING.md — fix before committing.\n'
        )

    sys.stdout.write(
        'Wrote CONTRIBUTING.md. Confirm: the `# Pull requests` type list matches '
        '.github/check-conventional-pr-title.py (chore, ci, docs, feat, fix, perf, refactor, '
        'revert, test).\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
